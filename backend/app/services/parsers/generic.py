"""Generic CSV parser — fallback when no registered parser matches.

OOP concept: this is NOT registered in the registry. It's the fallback
that ParserRegistry.resolve() returns when no specific parser claims the file.

It also overrides _validate_headers() to add an extra check — since it's
a fallback, it can't guarantee columns are present like Chase/Stripe can.
"""

from typing import Optional

from app.services.parsers.base import BaseParser

_REQUIRED_COLUMNS: set[str] = {"date", "description", "amount"}


class GenericParser(BaseParser):
    """Fallback parser for any CSV with date, description, amount columns.

    Unlike Chase/Stripe parsers:
      - Not registered (not decorated with @ParserRegistry.register)
      - ParserRegistry returns it as last resort
      - Adds a header validation step since it doesn't have a specific signature
    """

    source_name = "generic"

    def can_handle(self, headers: set[str]) -> bool:
        return _REQUIRED_COLUMNS.issubset(headers)

    def normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        """No remapping needed — generic CSV already uses our standard names."""
        return row

    def _validate_headers(self, headers: set[str]) -> Optional[str]:
        """Override: check required columns are present before parsing rows.

        Chase/Stripe parsers don't need this because can_handle() already
        guarantees the right columns. GenericParser is a catch-all, so we
        do an explicit check here.
        """
        missing = _REQUIRED_COLUMNS - headers
        if missing:
            return f"Missing required columns: {', '.join(sorted(missing))}"
        return None
