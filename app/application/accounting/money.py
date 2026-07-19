"""Money helpers.

All monetary amounts in the ledger are :class:`decimal.Decimal` quantized to two
places (matching ``NUMERIC(14,2)``). Floats never touch the books — the agent may
*choose an account*, but every amount originates from stored data and is carried as
Decimal end to end. This module is the one place that decides rounding.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

Numeric = Union[int, float, str, Decimal]


def to_money(value: Numeric) -> Decimal:
    """Coerce a numeric value to a 2-dp Decimal using banker-free HALF_UP rounding.

    Strings and ints are exact; floats are converted via ``str`` first to avoid
    binary-float artefacts (e.g. ``0.1 + 0.2``).
    """
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, float):
        dec = Decimal(str(value))
    else:
        dec = Decimal(value)
    return dec.quantize(CENTS, rounding=ROUND_HALF_UP)
