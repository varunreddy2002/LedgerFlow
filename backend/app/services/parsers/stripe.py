"""Stripe payout report CSV parser.

OOP concepts:
  - Inheritance  : StripeParser extends BaseParser, gets parse() for free
  - Polymorphism : overrides is_always_inflow() — same method name,
                   different answer than ChaseParser (True vs False)
"""

from app.services.parsers.base import BaseParser
from app.services.parsers.registry import ParserRegistry


@ParserRegistry.register
class StripeParser(BaseParser):
    """Parses Stripe payout report CSV exports.

    Stripe exports these columns:
        id, Type, Amount, Fee, Net, Currency, Created (UTC), Description, Transfer

    The Net column is always a payout amount → every row is an INFLOW.
    """

    source_name = "stripe"

    _SIGNATURE: set[str] = {"id", "type", "amount", "fee", "net", "currency", "created (utc)"}

    _COLUMN_MAP: dict[str, str] = {
        "created (utc)": "date",
        "description": "description",
        "net": "amount",   # use Net (after fees), not gross Amount
    }

    def can_handle(self, headers: set[str]) -> bool:
        return self._SIGNATURE.issubset(headers)

    def normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        return {self._COLUMN_MAP.get(k, k): v for k, v in row.items()}

    def is_always_inflow(self) -> bool:
        """Stripe net is always a payout — override to True.

        POLYMORPHISM: same method as ChaseParser, but different behavior.
        The base parse() calls this without knowing which parser it is.
        """
        return True
