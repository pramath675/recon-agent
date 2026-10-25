import pytest
from tax.calculator import calculate_tax


def test_zero_income():
    assert calculate_tax(0.0) == 0.0


def test_tier_1_exempt():
    assert calculate_tax(5000.0) == 0.0
    assert calculate_tax(10000.0) == 0.0


def test_tier_2_bracket():
    # 30000 -> 20000 in tier 2 at 10% = 2000.0
    assert calculate_tax(30000.0) == 2000.0
    # 50000 -> 40000 in tier 2 at 10% = 4000.0
    assert calculate_tax(50000.0) == 4000.0


def test_negative_income_raises():
    with pytest.raises(ValueError):
        calculate_tax(-100.0)
