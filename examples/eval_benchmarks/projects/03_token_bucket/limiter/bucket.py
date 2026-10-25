"""Token bucket rate limiter implementation."""
from __future__ import annotations


class TokenBucket:
    """A token bucket rate limiter with a fixed capacity and refill rate."""

    def __init__(self, capacity: float, refill_rate: float):
        if capacity <= 0 or refill_rate <= 0:
            raise ValueError("capacity and refill_rate must be positive")
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_update = 0.0

    def refill(self, current_time: float) -> None:
        """Refill tokens based on elapsed time."""
        if current_time < self.last_update:
            return
        elapsed = current_time - self.last_update
        self.last_update = current_time
        # BUG: Fails to clamp self.tokens to self.capacity.
        # If the bucket is idle, tokens accumulate indefinitely beyond capacity.
        self.tokens += elapsed * self.refill_rate

    def consume(self, amount: float, current_time: float) -> bool:
        """Attempt to consume tokens at current_time. Returns True if allowed."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.refill(current_time)
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False
