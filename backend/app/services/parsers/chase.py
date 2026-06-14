"""Chase bank statement CSV parser.

OOP concepts:
  - Inheritance  : ChaseParser extends BaseParser, gets parse() for free
  - Polymorphism : same can_handle() interface, Chase-specific logic inside
  - Encapsulation: _SIGNATURE and _COLUMN_MAP are class-private constants
"""

from app.services.parsers.base import BaseParser
from app.services.parsers.registry import ParserRegistry


@ParserRegistry.register
class ChaseParser(BaseParser):
    """Parses Chase bank statement CSV exports.

    Chase exports these columns (lowercased after normalization):
        Transaction Date, Post Date, Description, Category, Type, Amount, Memo
    """

    source_name = "chase"

    # Minimum headers that must ALL be present to identify a Chase file
    _SIGNATURE: set[str] = {"transaction date", "post date", "description", "type", "amount"}

    # Maps Chase column names → our standard names
    _COLUMN_MAP: dict[str, str] = {
        "transaction date": "date",
        "description": "description",
        "amount": "amount",
        "memo": "notes",
    }

    def can_handle(self, headers: set[str]) -> bool:
        """Return True only if ALL required Chase columns are present."""
        return self._SIGNATURE.issubset(headers)

    def normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        """Rename Chase columns to our standard names.

        Columns not in _COLUMN_MAP pass through unchanged.
        """
        return {self._COLUMN_MAP.get(k, k): v for k, v in row.items()}
