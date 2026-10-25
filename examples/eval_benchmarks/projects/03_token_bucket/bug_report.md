# TokenBucket allows bursts exceeding capacity after idle time

When a `TokenBucket` sits idle for a long duration, refilled tokens accumulate beyond the bucket's maximum `capacity`.
For instance, with `capacity=5.0` and `refill_rate=1.0`, waiting 60 seconds allows an immediate burst of 60 tokens, when it should never exceed 5.0 tokens.
`refill` must cap `tokens` at `capacity`.
