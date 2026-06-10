"""Pure-function CSV parsing service — no DB access, no side effects.

Fixed column format (headers are case-insensitive):
  Required : date, description, amount
  Optional : account, notes

Amount sign convention:
  positive  →  inflow  (money received)
  negative  →  outflow (money spent)

The caller is responsible for passing ``existing_fingerprints`` so that
transactions already in the DB are skipped automatically.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: set[str] = {"date", "description", "amount"}

# Tried in order; first match wins.
DATE_FORMATS: list[str] = [
    "%Y-%m-%d",   # ISO  — 2025-01-15
    "%m/%d/%Y",   # US   — 01/15/2025
    "%m/%d/%y",   # US short — 01/15/25
    "%d/%m/%Y",   # EU   — 15/01/2025
    "%d-%m-%Y",   # EU dash — 15-01-2025
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RowError:
    row_number: int
    reason: str
    raw_value: str = ""


@dataclass
class ParseResult:
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_fingerprints: int = 0
    errors: list[RowError] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> Optional[Decimal]:
    """Strip common currency noise and parse to Decimal."""
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
    """Stable SHA-256 hash of the economic identity of a transaction row.

    Same business + same date + same description + same amount → same hash,
    regardless of which file the row came from.  Used for cross-file dedup.
    """
    raw = f"{business_id}:{txn_date.isoformat()}:{description.strip().lower()}:{abs(amount)}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_csv(
    file_content: bytes,
    business_id: int,
    document_id: int,
    existing_fingerprints: set[str] | None = None,
) -> ParseResult:
    """Parse raw CSV bytes into a list of unsaved ``Transaction`` ORM objects.

    Args:
        file_content:          Raw file bytes (may have UTF-8-BOM from Excel).
        business_id:           Business this upload belongs to.
        document_id:           The ``documents.id`` already created for this file.
        existing_fingerprints: Fingerprints already stored in the DB for this
                               business — rows matching these are skipped.

    Returns:
        ``ParseResult`` with ready-to-add ORM objects and a counts summary.
        Nothing is written to the DB; the caller commits.
    """
    result = ParseResult()
    seen: set[str] = set(existing_fingerprints or [])

    # Decode — handle BOM produced by Excel "Save as CSV UTF-8"
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    # ---- Header validation ------------------------------------------------
    if not reader.fieldnames:
        result.errors.append(RowError(0, "File is empty or has no header row"))
        return result

    headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        result.errors.append(
            RowError(0, f"Missing required columns: {', '.join(sorted(missing))}")
        )
        return result

    # ---- Row iteration ----------------------------------------------------
    for row_num, raw_row in enumerate(reader, start=2):  # row 1 = header
        # Normalize keys to lowercase so callers can use any casing
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}

        # --- date ---
        txn_date = _parse_date(row.get("date", ""))
        if txn_date is None:
            result.errors.append(
                RowError(row_num, f"Cannot parse date", raw_value=row.get("date", ""))
            )
            result.rows_skipped += 1
            continue

        # --- amount ---
        raw_amount = _parse_amount(row.get("amount", ""))
        if raw_amount is None:
            result.errors.append(
                RowError(row_num, "Cannot parse amount", raw_value=row.get("amount", ""))
            )
            result.rows_skipped += 1
            continue

        if raw_amount == Decimal("0"):
            # Zero-amount rows carry no financial meaning — skip silently
            result.rows_skipped += 1
            continue

        # --- description ---
        description = row.get("description", "")
        if not description:
            result.errors.append(RowError(row_num, "Description is empty"))
            result.rows_skipped += 1
            continue

        # --- derive direction from sign ---
        direction = Direction.INFLOW if raw_amount > 0 else Direction.OUTFLOW
        amount = abs(raw_amount)

        # --- fingerprint / dedup ---
        fp = _fingerprint(business_id, txn_date, description, amount)
        if fp in seen:
            result.duplicate_fingerprints += 1
            result.rows_skipped += 1
            continue
        seen.add(fp)

        # --- optional fields ---
        notes = row.get("notes", "") or None

        # Build ORM object — not added to session here
        txn = Transaction(
            business_id=business_id,
            document_id=document_id,
            transaction_date=txn_date,
            description_raw=description,
            amount=amount,
            direction=direction,
            transaction_type=TransactionType.UNKNOWN,
            review_status=ReviewStatus.NEEDS_REVIEW,
            fingerprint_hash=fp,
            is_excluded_from_pnl=False,
            notes=notes,
        )
        result.transactions.append(txn)
        result.rows_imported += 1

    return result
