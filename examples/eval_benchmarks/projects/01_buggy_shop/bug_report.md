# Bulk discount is not applied at exactly 10 units

The docs for `line_total` say that orders of 10 or more units get a 10% bulk discount.
But `line_total(10.0, 10)` returns 100.0 instead of 90.0. Orders of 11+ units are discounted correctly.
