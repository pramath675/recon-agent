import io
import json
import urllib.error

import pytest

from recon import llm as llm_mod
from recon.config import Config
from recon.llm import BudgetExhausted, LLMClient, LLMError, extract_json

CFG = Config(api_key="k-123", base_url="https://example.invalid/v1/", model="m", max_api_calls=2)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def reply(content, usage=None, finish="stop"):
    body = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    if usage:
        body["usage"] = usage
    return FakeResp(json.dumps(body).encode())


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 1} hope it helps') == {"a": 1}
    for bad in ("no json", "{broken", "[1, 2]"):
        with pytest.raises(LLMError):
            extract_json(bad)


def test_budget_is_enforced_and_no_retry(monkeypatch):
    calls = []
    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout, json.loads(req.data)))
        return reply('{"ok": true}', usage={"prompt_tokens": 10, "completion_tokens": 5})
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", fake_urlopen)
    c = LLMClient(CFG)
    assert c.complete_json("a", "s", "u") == {"ok": True}
    c.complete_json("b", "s", "u")
    with pytest.raises(BudgetExhausted):
        c.complete_json("c", "s", "u")
    assert len(calls) == 2
    url, timeout, body = calls[0]
    assert url == "https://example.invalid/v1/chat/completions" and timeout == CFG.http_timeout
    assert body["max_tokens"] == CFG.max_output_tokens and body["temperature"] == 0
    assert c.usage.prompt_tokens == 20 and c.usage.completion_tokens == 10


def test_http_error_not_retried_and_key_never_leaks(monkeypatch):
    attempts = []
    def boom(req, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"bad key k-123"))
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
    c = LLMClient(CFG)
    with pytest.raises(LLMError) as exc:
        c.complete_json("a", "s", "u")
    assert len(attempts) == 1 and "k-123" not in str(exc.value) and c.usage.calls == 1


def test_truncated_and_empty_output_are_errors(monkeypatch):
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", lambda r, timeout: reply('{"a":', finish="length"))
    with pytest.raises(LLMError, match="cut off"):
        LLMClient(CFG).complete_json("a", "s", "u")
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", lambda r, timeout: reply(""))
    with pytest.raises(LLMError, match="empty"):
        LLMClient(CFG).complete_json("a", "s", "u")
