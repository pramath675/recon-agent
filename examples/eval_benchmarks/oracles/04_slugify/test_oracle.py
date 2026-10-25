"""Independent oracle test for 04_slugify.

Kept outside the project directory received by RECON.
Verifies that truncated slugs do not retain a trailing hyphen.
"""
import pytest
from slug.formatter import slugify


def test_oracle_hyphen_boundary_truncation():
    # 'quick brown fox jumps' -> 'quick-brown-fox-jumps'
    # Truncated to 12 chars: 'quick-brown-'
    # Expected: 'quick-brown' (11 chars, trailing hyphen stripped).
    # On original buggy code, returns 'quick-brown-' (FAILS).
    assert slugify("quick brown fox jumps", max_len=12) == "quick-brown"


def test_oracle_second_boundary_truncation():
    # 'alpha beta gamma' -> 'alpha-beta-gamma'
    # Truncated to 11 chars: 'alpha-beta-'
    # Expected: 'alpha-beta'.
    # On original buggy code, returns 'alpha-beta-' (FAILS).
    assert slugify("alpha beta gamma", max_len=11) == "alpha-beta"


def test_oracle_never_ends_with_hyphen():
    result = slugify("one two three", max_len=8)  # 'one-two-three'[:8] == 'one-two-'
    assert not result.endswith("-")
