"""Decimal helpers for money and quantities.

Everything monetary is Decimal with 4 decimal places, matching NUMERIC(18,4) in
the database. Rounding is HALF_UP, which is what invoices expect -- Python's
default (HALF_EVEN) would drift against the accounting the customer sees.
"""

from decimal import ROUND_HALF_UP, Decimal

SCALE = Decimal("0.0001")
ZERO = Decimal("0")


def money(value: Decimal | int | str) -> Decimal:
    """Normalise a value to the money scale."""
    return Decimal(value).quantize(SCALE, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | int | str) -> Decimal:
    """Quantities share the money scale: products may be sold by weight."""
    return Decimal(value).quantize(SCALE, rounding=ROUND_HALF_UP)
