"""CSV parsing — decode raw bytes into unsaved Transaction ORM objects.

A single, flat parser. It expects three standard columns (case-insensitive):

    date, description, amount

The pipeline:
  1. Decode bytes → text (handles Excel's UTF-8-BOM and latin-1)
  2. Validate the required columns are present
  3. For each row: parse date, parse amount, derive direction,
     fingerprint for dedup, build a Transaction
  4. Return a ParseResult — the caller is responsible for the DB commit

Nothing is written to the database here.
"""

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.models.enums import Direction, ReviewStatus, TransactionType
from app.models.transaction import Transaction

# Date formats tried in order — first match wins.
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",              # ISO        — 2025-01-15
    "%m/%d/%Y",              # US         — 01/15/2025
    "%m/%d/%y",              # US short   — 01/15/25
    "%d/%m/%Y",              # EU         — 15/01/2025
    "%d-%m-%Y",              # EU dash    — 15-01-2025
    "%Y-%m-%d %H:%M:%S %Z",  # UTC stamp  — 2025-01-15 12:34:56 UTC
    "%Y-%m-%d %H:%M:%S",     # ISO datetime
]

_REQUIRED_COLUMNS: set[str] = {"date", "description", "amount"}


# ---------------------------------------------------------------------------
# Result types — consumed by the routes and DocumentService
# ---------------------------------------------------------------------------

@dataclass
class RowError:
    """A single row-level parse failure."""
    row_number: int
    reason: str
    raw_value: str = ""


@dataclass
class ParseResult:
    """Everything parsing produces for one CSV file."""
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_fingerprints: int = 0
    errors: list[RowError] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_csv(
    file_content: bytes,
    business_id: int,
    document_id: int,
    existing_fingerprints: Optional[set[str]] = None,
) -> ParseResult:
    """Parse raw CSV bytes into a list of unsaved Transaction ORM objects."""
    result = ParseResult()
    seen: set[str] = set(existing_fingerprints or [])

    text = _decode(file_content)
    reader = csv.DictReader(io.StringIO(text))

    # Guard: empty or header-only file
    if not reader.fieldnames:
        result.errors.append(RowError(0, "File is empty or has no header row"))
        return result

    headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing = _REQUIRED_COLUMNS - headers
    if missing:
        result.errors.append(
            RowError(0, f"Missing required columns: {', '.join(sorted(missing))}")
        )
        return result

    # Row iteration starts at 2 (row 1 = header)
    for row_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}

        txn_date = _parse_date(row.get("date", ""))
        if txn_date is None:
            result.errors.append(RowError(row_num, "Cannot parse date", row.get("date", "")))
            result.rows_skipped += 1
            continue

        raw_amount = _parse_amount(row.get("amount", ""))
        if raw_amount is None:
            result.errors.append(RowError(row_num, "Cannot parse amount", row.get("amount", "")))
            result.rows_skipped += 1
            continue

        if raw_amount == Decimal("0"):
            result.rows_skipped += 1
            continue

        description = row.get("description", "")
        if not description:
            result.errors.append(RowError(row_num, "Description is empty"))
            result.rows_skipped += 1
            continue

        direction = Direction.INFLOW if raw_amount > 0 else Direction.OUTFLOW
        amount = abs(raw_amount)

        fp = _fingerprint(business_id, txn_date, description, amount)
        if fp in seen:
            result.duplicate_fingerprints += 1
            result.rows_skipped += 1
            continue
        seen.add(fp)

        result.transactions.append(Transaction(
            business_id=business_id,
            document_id=document_id,
            account_id=None,
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _decode(content: bytes) -> str:
    """Decode bytes, handling Excel's UTF-8-BOM variant."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


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


def _fingerprint(business_id: int, txn_date: date, description: str, amount: Decimal) -> str:
    raw = f"{business_id}:{txn_date.isoformat()}:{description.strip().lower()}:{abs(amount)}"
    return hashlib.sha256(raw.encode()).hexdigest()
