"""Progressive income tax calculation."""
from __future__ import annotations


def calculate_tax(income: float) -> float:
    """Calculate progressive income tax based on tiered brackets:
      - $0 to $10,000: 0%
      - $10,001 to $50,000: 10%
      - Over $50,000: 20%
    """
    if income < 0:
        raise ValueError("income must not be negative")
    if income <= 10000:
        return 0.0
    if income <= 50000:
        return round((income - 10000) * 0.10, 2)
    # Tier 1: 0 tax on first $10k
    # Tier 2: 10% on $40k ($10k to $50k) = $4,000
    tier2_tax = 4000.0
    # BUG: Applies 20% to total income above $10,000 instead of income above $50,000.
    # For $60,000, computes tier2_tax + (60000 - 10000) * 0.20 = 4000 + 10000 = 14000,
    # instead of tier2_tax + (60000 - 50000) * 0.20 = 4000 + 2000 = 6000.
    tier3_tax = (income - 10000) * 0.20
    return round(tier2_tax + tier3_tax, 2)
