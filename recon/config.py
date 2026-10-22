"""Configuration, loaded only from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no dependency). Real environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}")
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_api_calls: int = 4
    max_output_tokens: int = 1500
    max_context_chars: int = 24000
    http_timeout: int = 60
    test_timeout: int = 60
    repeats: int = 2

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            api_key=os.environ.get("NEBIUS_API_KEY", "").strip(),
            base_url=os.environ.get("NEBIUS_BASE_URL", "").strip(),
            model=os.environ.get("NEBIUS_MODEL", "").strip(),
            max_api_calls=_int_env("RECON_MAX_API_CALLS", 4, 1, 10),
            max_output_tokens=_int_env("RECON_MAX_OUTPUT_TOKENS", 1500, 200, 4000),
            max_context_chars=_int_env("RECON_MAX_CONTEXT_CHARS", 24000, 2000, 80000),
            http_timeout=_int_env("RECON_HTTP_TIMEOUT", 60, 5, 300),
            test_timeout=_int_env("RECON_TEST_TIMEOUT", 60, 5, 600),
            repeats=_int_env("RECON_REPEATS", 2, 1, 5),
        )

    def missing_api_settings(self) -> List[str]:
        missing = []
        if not self.api_key:
            missing.append("NEBIUS_API_KEY")
        if not self.base_url:
            missing.append("NEBIUS_BASE_URL")
        if not self.model:
            missing.append("NEBIUS_MODEL")
        return missing

    def with_max_calls(self, n: Optional[int]) -> "Config":
        if n is None:
            return self
        if not 1 <= n <= 10:
            raise ConfigError("--max-calls must be between 1 and 10")
        from dataclasses import replace
        return replace(self, max_api_calls=n)
