"""Independent oracle test for 02_semver.

Kept outside the project directory received by RECON.
Verifies that version comparison treats components as numerical integers rather than ASCII strings.
"""
import pytest
from semver.parser import compare


def test_oracle_multi_digit_minor_comparison():
    # 1.10.0 is strictly greater than 1.9.0.
    # On the original buggy code, string comparison treats '10' < '9', returning -1 (FAILS).
    assert compare("1.10.0", "1.9.0") == 1


def test_oracle_multi_digit_patch_comparison():
    # 2.0.10 is strictly greater than 2.0.9.
    # On the original buggy code, returns -1 (FAILS).
    assert compare("2.0.10", "2.0.9") == 1


def test_oracle_large_number_comparison():
    # 0.100.0 is strictly greater than 0.99.0.
    # On the original buggy code, returns -1 (FAILS).
    assert compare("0.100.0", "0.99.0") == 1
