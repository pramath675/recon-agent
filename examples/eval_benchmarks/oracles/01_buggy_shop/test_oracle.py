"""Independent oracle test for 01_buggy_shop.

Kept outside the project directory received by RECON.
Verifies that orders of exactly 10 units receive the 10% bulk discount ($90.00 instead of $100.00).
"""
import pytest
from shop.pricing import line_total


def test_oracle_bulk_discount_at_exact_threshold():
    # Exactly 10 units of $10.00 should receive a 10% discount: 10 * 10.0 * 0.90 = $90.00
    # On the original buggy code, this returns 100.0 (FAILS).
    assert line_total(10.0, 10) == 90.0


def test_oracle_boundary_integrity():
    # 9 units: no discount -> 9 * 10.0 = $90.00
    assert line_total(10.0, 9) == 90.0
    # 11 units: discounted -> 11 * 10.0 * 0.90 = $99.00
    assert line_total(10.0, 11) == 99.0
