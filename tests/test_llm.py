import io
import json
import urllib.error

import pytest

from recon import llm as llm_mod
from recon.config import Config
from recon.llm import BudgetExhausted, EmptyResponseError, LLMClient, LLMError, extract_json

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


def test_empty_response_retries_once_when_budget_allows(monkeypatch):
    """When the first response is empty and budget has headroom, retry once with reinforced prompt and record all tokens."""
    responses = [
        reply("", usage={"prompt_tokens": 100, "completion_tokens": 0}),  # Call 1: empty but consumed prompt tokens
        reply('{"fixed": true}', usage={"prompt_tokens": 150, "completion_tokens": 50}),  # Call 2: success
    ]
    calls = []

    def mock_urlopen(req, timeout):
        calls.append((req, json.loads(req.data)))
        return responses.pop(0)

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", mock_urlopen)
    # Budget of 3 calls has headroom after call 1
    client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=3))
    result = client.complete_json("patch", "system prompt", "user prompt")

    assert result == {"fixed": True}
    assert len(calls) == 2
    assert client.usage.calls == 2
    assert client.usage.stages == ["patch", "patch_retry"]
    # Ensure provider-reported tokens from the empty response are NOT silently omitted:
    assert client.usage.prompt_tokens == 250  # 100 from call 1 + 150 from call 2
    assert client.usage.completion_tokens == 50
    assert client.usage.calls_with_reported_usage == 2
    assert any("retrying once within remaining budget" in err for err in client.usage.errors)
    # Verify retry prompt includes reinforcement note:
    retry_req_body = calls[1][1]
    user_msg = retry_req_body["messages"][1]["content"]
    assert "[RECON System Note: The previous model response was empty." in user_msg


def test_empty_content_with_finish_reason_length_is_not_retried(monkeypatch):
    """When output is empty but finish_reason='length' (truncated), it must NOT be retried."""
    attempts = []

    def mock_urlopen(req, timeout):
        attempts.append(1)
        return reply("", finish="length", usage={"prompt_tokens": 300, "completion_tokens": 0})

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", mock_urlopen)
    # Generous budget of 5 calls: must still fail immediately as a length cutoff error without retrying
    client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=5))
    with pytest.raises(LLMError, match="cut off by max_tokens"):
        client.complete_json("patch", "sys", "usr")

    assert len(attempts) == 1
    assert client.usage.calls == 1
    assert client.usage.stages == ["patch"]


def test_empty_response_records_provider_reported_tokens_even_on_failure(monkeypatch):
    """Ensure provider-reported tokens on an un-retried empty response are preserved in usage accounting."""
    def mock_urlopen(req, timeout):
        return reply("", usage={"prompt_tokens": 420, "completion_tokens": 0})

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", mock_urlopen)
    client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=1))
    with pytest.raises(EmptyResponseError):
        client.complete_json("repro", "sys", "usr")

    assert client.usage.calls == 1
    assert client.usage.prompt_tokens == 420
    assert client.usage.completion_tokens == 0
    assert client.usage.calls_with_reported_usage == 1


def test_empty_response_does_not_retry_when_budget_exhausted(monkeypatch):
    """When budget has no headroom (max_calls=1 or already exhausted), do NOT retry."""
    calls = []

    def mock_urlopen(req, timeout):
        calls.append(req)
        return reply("")

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", mock_urlopen)

    # Budget of 1 call: call 1 fails with empty, no budget left to retry
    client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=1))
    with pytest.raises(EmptyResponseError, match="empty"):
        client.complete_json("repro", "sys", "usr")

    assert len(calls) == 1
    assert client.usage.calls == 1
    assert client.usage.stages == ["repro"]
    assert any("no budget remaining to retry" in err for err in client.usage.errors)


def test_empty_response_does_not_retry_when_budget_exhausted_on_second_stage(monkeypatch):
    """When stage 1 uses call 1 and stage 2 uses call 2 with max_calls=2, empty response in stage 2 cannot retry."""
    responses = [
        reply('{"repro": "ok"}', usage={"prompt_tokens": 10, "completion_tokens": 10}),
        reply(""),
    ]
    calls = []

    def mock_urlopen(req, timeout):
        calls.append(req)
        return responses.pop(0)

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", mock_urlopen)

    client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=2))
    assert client.complete_json("repro", "sys", "usr") == {"repro": "ok"}
    assert client.usage.calls == 1

    # Stage 2: call 2 of 2 is empty -> no budget remaining, halts immediately
    with pytest.raises(EmptyResponseError, match="empty"):
        client.complete_json("patch", "sys", "usr")

    assert len(calls) == 2
    assert client.usage.calls == 2
    assert client.usage.stages == ["repro", "patch"]
    assert any("no budget remaining to retry" in err for err in client.usage.errors)


def test_generic_llm_errors_never_retried_even_with_budget(monkeypatch):
    """Generic errors (HTTP 401, 404, timeout, truncation, invalid JSON) must NEVER retry."""
    attempts = []

    def make_urlopen(error_type):
        def _call(req, timeout):
            attempts.append(1)
            if error_type == "401":
                raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad auth"))
            elif error_type == "404":
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b"model not found"))
            elif error_type == "timeout":
                raise TimeoutError("timed out")
            elif error_type == "length":
                return reply('{"incomplete":', finish="length")
            elif error_type == "bad_json":
                return reply("I cannot help with that (no json)")
        return _call

    for err in ("401", "404", "timeout", "length", "bad_json"):
        attempts.clear()
        monkeypatch.setattr(llm_mod.urllib.request, "urlopen", make_urlopen(err))
        # Generous budget of 5 calls: must still make EXACTLY 1 attempt and raise immediately
        client = LLMClient(Config(api_key="k", base_url="https://example.invalid", model="m", max_api_calls=5))
        with pytest.raises(LLMError):
            client.complete_json("stage", "sys", "usr")
        assert len(attempts) == 1, f"Expected exactly 1 attempt for {err}, got {len(attempts)}"
        assert client.usage.calls == 1


def test_llm_docstring_accurately_describes_retry_policy():
    """Verify that recon.llm module docstring explicitly documents the empty response retry policy."""
    doc = llm_mod.__doc__ or ""
    assert "at most one bounded retry strictly for empty model responses" in doc
    assert "zero retries for generic errors, timeouts, or truncated responses" in doc


def test_harness_check_offline_exits_nonzero_on_variant_mismatch(monkeypatch, tmp_path):
    """Verify that eval_benchmark_harness exits nonzero if a follow-up variant reports MISMATCH."""
    import eval_benchmark_harness as harness

    bad_variant = [{
        "id": "variant_mismatch_test",
        "name": "Mismatch Variant",
        "domain": "Test",
        "bug_type": "None",
        "project_dir": harness.BENCHMARK_TASKS[0]["project_dir"],
        "bug_report": harness.BENCHMARK_TASKS[0]["bug_report"],
        "oracle_test": harness.BENCHMARK_TASKS[0]["oracle_test"],
        "reference_repro": tmp_path / "missing_repro.py",
    }]
    monkeypatch.setattr(harness, "FOLLOWUP_VARIANTS", bad_variant)
    exit_code = harness.check_offline_baseline_and_oracles()
    assert exit_code == 1, f"Expected exit code 1 for MISMATCH variant, got {exit_code}"
