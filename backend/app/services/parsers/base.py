"""Abstract base parser — the CONTRACT all CSV parsers must follow.

OOP concepts used here:
  - Abstraction   : BaseParser defines WHAT a parser does, not HOW
  - Encapsulation : shared helpers (_decode, _parse_date, etc.) are
                    private to this class — callers can't see them
  - Template Method pattern : parse() controls the overall pipeline;
                    subclasses only override specific steps
"""

import csv
import hashlib
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.models.enums import Direction, ReviewStatus, TransactionType
from app.models.transaction import Transaction

# ---------------------------------------------------------------------------
# Shared date formats — tried in order, first match wins
# ---------------------------------------------------------------------------

_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",               # ISO        — 2025-01-15
    "%m/%d/%Y",               # US         — 01/15/2025
    "%m/%d/%y",               # US short   — 01/15/25
    "%d/%m/%Y",               # EU         — 15/01/2025
    "%d-%m-%Y",               # EU dash    — 15-01-2025
    "%Y-%m-%d %H:%M:%S %Z",  # Stripe UTC — 2025-01-15 12:34:56 UTC
    "%Y-%m-%d %H:%M:%S",     # ISO datetime
]


# ---------------------------------------------------------------------------
# Data classes — shared result types used by all parsers and by the routes
# ---------------------------------------------------------------------------

@dataclass
class RowError:
    """Describes a single row-level parse failure."""
    row_number: int
    reason: str
    raw_value: str = ""


@dataclass
class ParseResult:
    """Everything the parser produces for one CSV file."""
    source: str = "generic"
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_fingerprints: int = 0
    errors: list[RowError] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base class — the contract
# ---------------------------------------------------------------------------

class BaseParser(ABC):
    """Contract that every CSV parser must implement.

    ABSTRACTION — this class defines WHAT every parser must do:
      1. Identify itself     → source_name (class attribute)
      2. Detect its format   → can_handle(headers) [ABSTRACT]
      3. Map column names    → normalize_row(row)  [ABSTRACT]

    TEMPLATE METHOD — parse() is the shared pipeline. Subclasses do NOT
    reimplement it; they only fill in the two abstract steps above.
    """

    # Subclasses MUST set this — e.g. "chase", "stripe"
    source_name: str

    # ------------------------------------------------------------------
    # Abstract methods — subclasses MUST implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def can_handle(self, headers: set[str]) -> bool:
        """Return True if this parser recognizes the header set.

        Called by ParserRegistry to auto-select the right parser.
        """

    @abstractmethod
    def normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        """Map source-specific column names → standard names.

        Standard names used downstream: date, description, amount, notes
        """

    # ------------------------------------------------------------------
    # Overridable hook — subclasses CAN override, but don't have to
    # ------------------------------------------------------------------

    def is_always_inflow(self) -> bool:
        """Return True for sources where every row is an inflow.

        Example: Stripe net column is always a payout → always INFLOW.
        Default is False.
        """
        return False

    def _validate_headers(self, headers: set[str]) -> Optional[str]:
        """Return an error message if headers are invalid, else None.

        The default implementation trusts can_handle() — if we got here,
        headers are already valid. Override in GenericParser which needs
        an extra check since it's a fallback, not a match.
        """
        return None

    # ------------------------------------------------------------------
    # Template Method — the shared parsing pipeline
    # Subclasses inherit this; they do NOT override it.
    # ------------------------------------------------------------------

    def parse(
        self,
        file_content: bytes,
        business_id: int,
        document_id: int,
        existing_fingerprints: Optional[set[str]] = None,
        account_map: Optional[dict[str, int]] = None,
    ) -> ParseResult:
        """Parse raw CSV bytes → list of unsaved Transaction ORM objects.

        TEMPLATE METHOD — controls the overall flow:
          1. Decode bytes → text
          2. Validate headers (subclass hook)
          3. For each row:
             a. normalize column names  (subclass step)
             b. parse date, amount, description
             c. compute fingerprint, skip duplicates
             d. build Transaction object
          4. Return ParseResult

        Nothing is written to the DB — the caller commits.
        """
        result = ParseResult(source=self.source_name)
        seen: set[str] = set(existing_fingerprints or [])
        account_id: Optional[int] = (account_map or {}).get(self.source_name)
        always_inflow = self.is_always_inflow()

        text = self._decode(file_content)
        reader = csv.DictReader(io.StringIO(text))

        # Guard: empty or header-only file
        if not reader.fieldnames:
            result.errors.append(RowError(0, "File is empty or has no header row"))
            return result

        headers = {h.strip().lower() for h in reader.fieldnames if h}

        # Subclass-specific header validation (e.g. GenericParser checks required cols)
        header_error = self._validate_headers(headers)
        if header_error:
            result.errors.append(RowError(0, header_error))
            return result

        # Row iteration starts at row 2 (row 1 = header)
        for row_num, raw_row in enumerate(reader, start=2):
            # Step A — normalize keys + remap to standard column names
            row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}
            row = self.normalize_row(row)

            # Step B — parse date
            txn_date = self._parse_date(row.get("date", ""))
            if txn_date is None:
                result.errors.append(RowError(row_num, "Cannot parse date", row.get("date", "")))
                result.rows_skipped += 1
                continue

            # Step B — parse amount
            raw_amount = self._parse_amount(row.get("amount", ""))
            if raw_amount is None:
                result.errors.append(RowError(row_num, "Cannot parse amount", row.get("amount", "")))
                result.rows_skipped += 1
                continue

            if raw_amount == Decimal("0"):
                result.rows_skipped += 1
                continue

            # Step B — description
            description = row.get("description", "")
            if not description:
                result.errors.append(RowError(row_num, "Description is empty"))
                result.rows_skipped += 1
                continue

            # Step B — direction
            direction = Direction.INFLOW if (always_inflow or raw_amount > 0) else Direction.OUTFLOW
            amount = abs(raw_amount)

            # Step C — fingerprint-based dedup
            fp = self._fingerprint(business_id, txn_date, description, amount)
            if fp in seen:
                result.duplicate_fingerprints += 1
                result.rows_skipped += 1
                continue
            seen.add(fp)

            # Step D — build Transaction (not yet added to DB session)
            result.transactions.append(Transaction(
                business_id=business_id,
                document_id=document_id,
                account_id=account_id,
                transaction_date=txn_date,
                description_raw=description,
                amount=amount,
                direction=direction,
                transaction_type=TransactionType.UNKNOWN,
                review_status=ReviewStatus.NEEDS_REVIEW,
                fingerprint_hash=fp,
                is_excluded_from_pnl=False,
                notes=row.get("notes") or None,
            ))
            result.rows_imported += 1

        return result

    # ------------------------------------------------------------------
    # Private helpers — ENCAPSULATION: hidden from outside callers
    # Marked with _ prefix → "internal use only" convention in Python
    # ------------------------------------------------------------------

    @staticmethod
    def _decode(content: bytes) -> str:
        """Decode bytes, handling Excel's UTF-8-BOM variant."""
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content.decode("latin-1")

    @staticmethod
    def _parse_date(value: str) -> Optional[date]:
        value = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_amount(value: str) -> Optional[Decimal]:
        cleaned = (
            value.strip()
            .replace(",", "")
            .replace("$", "")
            .replace("£", "")
            .replace("€", "")
            .replace(" ", "")
        )
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _fingerprint(business_id: int, txn_date: date, description: str, amount: Decimal) -> str:
        raw = f"{business_id}:{txn_date.isoformat()}:{description.strip().lower()}:{abs(amount)}"
        return hashlib.sha256(raw.encode()).hexdigest()
