"""Semantic version parsing and comparison utilities."""
from __future__ import annotations
from typing import Tuple


def parse_version(v: str) -> Tuple:
    """Parse a semver string like '1.2.3' into a comparable tuple.

    Expected: tuple of integers (e.g. (1, 2, 3)).
    """
    parts = v.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semver string: {v}")
    # BUG: Leaves version components as strings instead of converting each to int.
    # String comparison results in '10' < '9', so '1.10.0' is compared as older than '1.9.0'.
    return tuple(parts)


def compare(v1: str, v2: str) -> int:
    """Compare two semver strings.

    Returns:
        1 if v1 > v2
        0 if v1 == v2
       -1 if v1 < v2
    """
    p1 = parse_version(v1)
    p2 = parse_version(v2)
    if p1 > p2:
        return 1
    if p1 < p2:
        return -1
    return 0
