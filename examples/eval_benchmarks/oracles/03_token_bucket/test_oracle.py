"""Independent oracle test for 03_token_bucket.

Kept outside the project directory received by RECON.
Verifies that tokens refilled after idle time are clamped to bucket capacity.
"""
import pytest
from limiter.bucket import TokenBucket


def test_oracle_idle_refill_clamped_to_capacity():
    b = TokenBucket(capacity=5.0, refill_rate=1.0)
    # Drain the bucket completely at t=0
    assert b.consume(5.0, current_time=0.0) is True
    # Wait 60 seconds (idle period)
    # Refill should cap tokens at 5.0, so consuming 6.0 tokens MUST return False.
    # On the original buggy code, tokens accumulates to 60.0, returning True (FAILS).
    assert b.consume(6.0, current_time=60.0) is False


def test_oracle_idle_start_clamped_to_capacity():
    b = TokenBucket(capacity=5.0, refill_rate=1.0)
    # Even without initial drain, after 100 seconds idle, tokens cannot exceed 5.0
    b.refill(100.0)
    # On the original buggy code, tokens == 105.0 (FAILS).
    assert b.tokens <= 5.0
