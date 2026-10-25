import pytest
from limiter.bucket import TokenBucket


def test_initial_capacity_consumption():
    b = TokenBucket(capacity=5.0, refill_rate=1.0)
    assert b.consume(3.0, current_time=0.0) is True
    assert b.tokens == 2.0


def test_rejection_when_empty():
    b = TokenBucket(capacity=5.0, refill_rate=1.0)
    assert b.consume(6.0, current_time=0.0) is False
    assert b.tokens == 5.0


def test_normal_refill():
    b = TokenBucket(capacity=5.0, refill_rate=1.0)
    assert b.consume(5.0, current_time=0.0) is True
    assert b.tokens == 0.0
    # After 2 seconds, 2 tokens refilled
    assert b.consume(2.0, current_time=2.0) is True
    assert b.tokens == 0.0


def test_invalid_parameters():
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, refill_rate=1.0)
    with pytest.raises(ValueError):
        TokenBucket(capacity=5.0, refill_rate=-1.0)
