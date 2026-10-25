"""Follow-up benchmark variant: Deterministic reproduction test for 03_token_bucket.

This variant uses the explicit `current_time` parameter of TokenBucket instead of
wall-clock delays or sleep. It reproduces the bug deterministically and instantly:
- Drains the bucket at current_time=0.0
- Advances to current_time=60.0
- Asserts that tokens are clamped to capacity (consume(6.0, current_time=60.0) == False)

On the original buggy code:
  Tokens accumulate to 60.0 without clamping, so consume(6.0, current_time=60.0) returns True.
  The assertion fails cleanly with an AssertionError (assert True is False).

On the patched code:
  Tokens are clamped to capacity (5.0), so consume(6.0, current_time=60.0) returns False.
  The assertion passes cleanly.
"""
from limiter.bucket import TokenBucket


def test_idle_tokens_clamped_to_capacity():
    bucket = TokenBucket(capacity=5.0, refill_rate=1.0)
    # Drain initial capacity at current_time=0.0
    assert bucket.consume(5.0, current_time=0.0) is True
    # At current_time=60.0, refilled tokens must be capped at 5.0 (capacity).
    # Consuming 6.0 tokens must be rejected.
    assert bucket.consume(6.0, current_time=60.0) is False
