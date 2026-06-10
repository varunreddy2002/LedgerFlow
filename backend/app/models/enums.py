"""Enumerations shared by ORM models and Pydantic schemas.

Each constrained column in the spec maps to exactly one Enum here.
All enums use StrEnum (Python 3.11+) so they:
  - Serialize cleanly to JSON (no .value needed)
  - Compare equal to plain strings ("inflow" == Direction.INFLOW)
  - Follow Python naming convention: UPPERCASE members, lowercase stored values
"""

from enum import StrEnum


class SourceType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    CREDIT_CARD_STATEMENT = "credit_card_statement"
    RECEIPT = "receipt"
    INVOICE = "invoice"
    VENDOR_BILL = "vendor_bill"
    PAYOUT_REPORT = "payout_report"
    UNKNOWN = "unknown"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CATEGORIZING = "categorizing"   # CSV parsed, background categorization running
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE_FILE = "duplicate_file"
    PENDING_OCR = "pending_ocr"
    NEEDS_REVIEW = "needs_review"


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    OTHER = "other"


class CategoryType(StrEnum):
    REVENUE = "revenue"
    COGS = "cogs"
    EXPENSE = "expense"
    EQUITY = "equity"
    TRANSFER = "transfer"
    LIABILITY = "liability"
    ASSET = "asset"
    NON_PNL = "non_pnl"


class Direction(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class TransactionType(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    OWNER_DRAW = "owner_draw"
    OWNER_CONTRIBUTION = "owner_contribution"
    LOAN_PAYMENT = "loan_payment"
    REFUND = "refund"
    TAX_PAYMENT = "tax_payment"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    AUTO_APPROVED = "auto_approved"
    NEEDS_REVIEW = "needs_review"
    USER_APPROVED = "user_approved"
    USER_CORRECTED = "user_corrected"
    IGNORED = "ignored"


class DuplicateMatchType(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"


class DuplicateGroupStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"


class DuplicateResolution(StrEnum):
    KEEP_ONE = "keep_one"        # confirmed duplicates — kept the primary, excluded rest
    KEEP_ALL = "keep_all"        # decided they are NOT duplicates — all transactions kept
    EXCLUDE_ALL = "exclude_all"  # all transactions excluded (edge case)


class ReviewIssueType(StrEnum):
    LOW_CONFIDENCE_CATEGORY = "low_confidence_category"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    POSSIBLE_TRANSFER = "possible_transfer"
    POSSIBLE_PERSONAL_EXPENSE = "possible_personal_expense"
    LARGE_TRANSACTION = "large_transaction"
    MISSING_VENDOR = "missing_vendor"
    MISSING_CUSTOMER = "missing_customer"
    UNCLEAR_COGS_OR_EXPENSE = "unclear_cogs_or_expense"
    UNCATEGORIZED = "uncategorized"


class ReviewItemStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ChatRole(StrEnum):
    USER = "user"
    BOT = "bot"
