# Version 1.10.0 compares as older than 1.9.0

Comparing semantic versions fails when minor or patch numbers have multiple digits.
For example, `compare("1.10.0", "1.9.0")` returns `-1` instead of `1`.
`parse_version` appears to sort components lexicographically as strings rather than numerically as integers.
