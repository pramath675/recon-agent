import pytest

from shop.pricing import cart_total, line_total


def test_single_unit_has_no_discount():
    assert line_total(5.0, 1) == 5.0


def test_large_order_gets_bulk_discount():
    assert line_total(10.0, 20) == 180.0


def test_cart_total_adds_lines():
    assert cart_total([(2.0, 3), (1.5, 2)]) == 9.0


def test_negative_quantity_rejected():
    with pytest.raises(ValueError):
        line_total(1.0, -1)
