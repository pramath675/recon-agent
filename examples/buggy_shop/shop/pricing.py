"""Tiny pricing helpers used as the RECON demo project (contains a deliberate bug)."""

BULK_THRESHOLD = 10
BULK_DISCOUNT = 0.10


def line_total(unit_price: float, quantity: int) -> float:
    """Total for one order line.

    Orders of BULK_THRESHOLD (10) or more units get a 10% bulk discount.
    """
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    total = unit_price * quantity
    if quantity > BULK_THRESHOLD:  # BUG: should be >=, exactly 10 units must be discounted
        total *= 1 - BULK_DISCOUNT
    return round(total, 2)


def cart_total(lines) -> float:
    """Sum of line totals for an iterable of (unit_price, quantity) pairs."""
    return round(sum(line_total(price, qty) for price, qty in lines), 2)
