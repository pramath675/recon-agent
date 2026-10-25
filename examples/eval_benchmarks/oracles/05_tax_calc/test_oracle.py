"""Independent oracle test for 05_tax_calc.

Kept outside the project directory received by RECON.
Verifies that income in the top bracket is taxed only on the marginal amount above $50,000.
"""
import pytest
from tax.calculator import calculate_tax


def test_oracle_tier_3_marginal_tax():
    # $60,000 income:
    #   $0-$10k: $0
    #   $10k-$50k: $4,000 (10% of $40k)
    #   $50k-$60k: $2,000 (20% of $10k)
    # Total expected: $6,000.00
    # On the original buggy code, returns 14000.00 (FAILS).
    assert calculate_tax(60000.0) == 6000.0


def test_oracle_tier_3_larger_income():
    # $70,000 income: $4,000 + (20,000 * 0.20) = $8,000.00
    # On the original buggy code, returns 16000.00 (FAILS).
    assert calculate_tax(70000.0) == 8000.0


def test_oracle_six_figure_income():
    # $100,000 income: $4,000 + (50,000 * 0.20) = $14,000.00
    # On the original buggy code, returns 22000.00 (FAILS).
    assert calculate_tax(100000.0) == 14000.0
