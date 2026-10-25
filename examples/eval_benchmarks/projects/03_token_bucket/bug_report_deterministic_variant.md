# TokenBucket allows bursts exceeding capacity after idle time (Deterministic Variant)

> **Follow-up Variant Note**: This follow-up variant specifies reproduction using the explicit `current_time` parameter of `TokenBucket`, preventing models from attempting non-deterministic wall-clock delays or sleep loops that exceeded output token limits in the initial evaluation.

When a `TokenBucket` sits idle for a long duration, refilled tokens accumulate beyond the bucket's maximum `capacity`.

Test this deterministically using the explicit `current_time` parameter:
- Initialize `TokenBucket(capacity=5.0, refill_rate=1.0)`
- Drain at `current_time=0.0` with `consume(5.0, current_time=0.0)` (returns `True`)
- Advance to `current_time=60.0`: `consume(6.0, current_time=60.0)` must return `False` because tokens cannot exceed capacity (`5.0`).

On the buggy code, `consume(6.0, current_time=60.0)` returns `True` because `refill` fails to cap `tokens` at `capacity`.
`refill` must clamp `tokens` to `capacity`.
