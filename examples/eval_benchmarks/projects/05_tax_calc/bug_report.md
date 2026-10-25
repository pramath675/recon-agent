# Progressive tax calculation overcharges top bracket income

For income above $50,000, `calculate_tax` applies the 20% rate to `(income - 10000)` instead of `(income - 50000)`.
For example, `calculate_tax(60000)` returns 14,000.0 instead of 6,000.0 ($4,000 for the $10k–$50k tier plus $2,000 for the $10k in the top tier).
