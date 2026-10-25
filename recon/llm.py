"""Bounded LLM client (OpenAI-compatible chat/completions over plain HTTPS).

Cost controls implemented here:
  * hard application-level call budget (a call is counted BEFORE it is sent)
  * max_tokens on every request, temperature 0
  * explicit HTTP timeout
  * at most one bounded retry strictly for empty model responses when budget remains (zero retries for generic errors, timeouts, or truncated responses)
  * token usage logged when the provider reports it

These are application-level limits only. They are not an account-wide
spending cap; promotional credits may not stop billing by themselves.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config


class LLMError(Exception):
    """Any failure talking to (or understanding) the model."""


class EmptyResponseError(LLMError):
    """The model returned an empty content payload."""

    def __init__(self, message: str, usage: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.usage = usage


class BudgetExhausted(LLMError):
    """The application-level API-call budget has been used up."""


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls_with_reported_usage: int = 0
    errors: List[str] = field(default_factory=list)
    stages: List[str] = field(default_factory=list)

    def to_dict(self, max_calls: int) -> Dict[str, Any]:
        return {
            "calls_made": self.calls,
            "max_calls_budget": max_calls,
            "prompt_tokens_reported": self.prompt_tokens,
            "completion_tokens_reported": self.completion_tokens,
            "calls_with_reported_usage": self.calls_with_reported_usage,
            "stages": list(self.stages),
            "errors": list(self.errors),
            "note": (
                "Application-level counters only. They are not a hard account-wide spending cap; "
                "check your Nebius console for actual usage and billing."
            ),
        }


def extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object from a model reply, tolerating code fences and stray prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("model reply contained no JSON object")
    try:
        obj = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"model reply was not valid JSON: {exc}")
    if not isinstance(obj, dict):
        raise LLMError("model reply JSON was not an object")
    return obj


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.usage = Usage()

    @property
    def model_name(self) -> str:
        return self.cfg.model

    def _record_usage(self, usage: Optional[Dict[str, Any]]) -> None:
        if usage:
            self.usage.calls_with_reported_usage += 1
            self.usage.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.usage.completion_tokens += int(usage.get("completion_tokens", 0) or 0)

    def complete_json(self, stage: str, system: str, user: str) -> Dict[str, Any]:
        if self.usage.calls >= self.cfg.max_api_calls:
            raise BudgetExhausted(
                f"API-call budget exhausted ({self.usage.calls}/{self.cfg.max_api_calls}); "
                f"refusing to call the model for stage '{stage}'"
            )
        self.usage.calls += 1          # counted before sending: failures still consume budget
        self.usage.stages.append(stage)
        try:
            text, usage = self._send(stage, system, user)
            self._record_usage(usage)
        except EmptyResponseError as exc:
            self._record_usage(exc.usage)
            # If and only if the configured API-call budget has room, retry once with reinforced prompt
            if self.usage.calls < self.cfg.max_api_calls:
                self.usage.errors.append(f"{stage}: {exc} (retrying once within remaining budget)")
                self.usage.calls += 1  # count the retry request before sending
                self.usage.stages.append(f"{stage}_retry")
                retry_user = (
                    f"{user}\n\n[RECON System Note: The previous model response was empty. "
                    f"Please output a complete, valid JSON object following the schema without markdown fences or extraneous commentary.]"
                )
                try:
                    text, retry_usage = self._send(stage, system, retry_user)
                    self._record_usage(retry_usage)
                except EmptyResponseError as retry_empty:
                    self._record_usage(retry_empty.usage)
                    self.usage.errors.append(f"{stage}_retry: {retry_empty}")
                    raise
                except LLMError as retry_exc:
                    self.usage.errors.append(f"{stage}_retry: {retry_exc}")
                    raise
            else:
                self.usage.errors.append(f"{stage}: {exc} (no budget remaining to retry)")
                raise
        except LLMError as exc:
            self.usage.errors.append(f"{stage}: {exc}")
            raise
        try:
            return extract_json(text)
        except LLMError as exc:
            self.usage.errors.append(f"{stage}: {exc}")
            raise

    # -- transport ------------------------------------------------------
    def _send(self, stage: str, system: str, user: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps({
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": self.cfg.max_output_tokens,
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.cfg.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.http_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace") if hasattr(exc, "read") else ""
            raise LLMError(f"HTTP {exc.code} from API: {detail}".replace(self.cfg.api_key, "***"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"network error or timeout: {exc}".replace(self.cfg.api_key, "***"))
        except json.JSONDecodeError:
            raise LLMError("API returned a non-JSON HTTP body")
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("unexpected API response shape (no choices[0].message.content)")
        usage = data.get("usage")
        # Check finish_reason == "length" before classifying empty content,
        # so truncated responses are never classified as empty or retried.
        if choice.get("finish_reason") == "length":
            raise LLMError("model output was cut off by max_tokens; raise RECON_MAX_OUTPUT_TOKENS")
        if not content:
            raise EmptyResponseError("model returned empty content", usage=usage)
        return content, usage


class FixtureLLM(LLMClient):
    """Offline stand-in that replays canned responses from a directory. Zero network, zero credits.

    Directory layout: repro_test.txt (the generated test source) and patch.json ({"edits": [...]}).
    Only the first-attempt stages exist; 'repair' stages raise, which exercises the safe-stop path.
    """

    def __init__(self, directory: Path, max_calls: int = 2):
        super().__init__(Config(max_api_calls=max_calls, model="offline-fixtures"))
        self.directory = Path(directory)

    def _send(self, stage: str, system: str, user: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        if stage == "repro":
            code = (self.directory / "repro_test.txt").read_text(encoding="utf-8")
            return json.dumps({"explanation": "canned fixture", "test_code": code}), None
        if stage == "patch":
            return (self.directory / "patch.json").read_text(encoding="utf-8"), None
        raise LLMError(f"offline fixtures have no response for stage '{stage}'")
