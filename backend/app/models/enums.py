"""Enumerations shared by ORM models and Pydantic schemas.

Each constrained column in the spec maps to exactly one Enum here. Defining the
allowed values once (instead of repeating string literals across models, schemas
and validation) keeps the database CHECK constraints and the API contract in
perfect sync. All enums subclass `str` so they serialize cleanly to JSON and
compare equal to their plain-string values.
"""

import enum


class SourceType(str, enum.Enum):
    bank_statement = "bank_statement"
    credit_card_statement = "credit_card_statement"
    receipt = "receipt"
    invoice = "invoice"
    vendor_bill = "vendor_bill"
    payout_report = "payout_report"
    unknown = "unknown"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    processed = "processed"
    failed = "failed"
    duplicate_file = "duplicate_file"
    pending_ocr = "pending_ocr"
    needs_review = "needs_review"


class AccountType(str, enum.Enum):
    checking = "checking"
    savings = "savings"
    credit_card = "credit_card"
    cash = "cash"
    paypal = "paypal"
    stripe = "stripe"
    other = "other"


class CategoryType(str, enum.Enum):
    revenue = "revenue"
    cogs = "cogs"
    expense = "expense"
    equity = "equity"
    transfer = "transfer"
    liability = "liability"
    asset = "asset"
    non_pnl = "non_pnl"


class Direction(str, enum.Enum):
    inflow = "inflow"
    outflow = "outflow"


class TransactionType(str, enum.Enum):
    revenue = "revenue"
    expense = "expense"
    transfer = "transfer"
    owner_draw = "owner_draw"
    owner_contribution = "owner_contribution"
    loan_payment = "loan_payment"
    refund = "refund"
    tax_payment = "tax_payment"
    unknown = "unknown"


class ReviewStatus(str, enum.Enum):
    auto_approved = "auto_approved"
    needs_review = "needs_review"
    user_approved = "user_approved"
    user_corrected = "user_corrected"
    ignored = "ignored"


class DuplicateMatchType(str, enum.Enum):
    exact = "exact"
    fuzzy = "fuzzy"


class DuplicateStatus(str, enum.Enum):
    pending_review = "pending_review"
    confirmed_duplicate = "confirmed_duplicate"
    rejected_duplicate = "rejected_duplicate"
    auto_confirmed = "auto_confirmed"


class ResolvedAction(str, enum.Enum):
    keep_both = "keep_both"
    exclude_transaction_1 = "exclude_transaction_1"
    exclude_transaction_2 = "exclude_transaction_2"


class ReviewIssueType(str, enum.Enum):
    low_confidence_category = "low_confidence_category"
    possible_duplicate = "possible_duplicate"
    possible_transfer = "possible_transfer"
    possible_personal_expense = "possible_personal_expense"
    large_transaction = "large_transaction"
    missing_vendor = "missing_vendor"
    missing_customer = "missing_customer"
    unclear_cogs_or_expense = "unclear_cogs_or_expense"
    uncategorized = "uncategorized"


class ReviewItemStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ChatRole(str, enum.Enum):
    user = "user"
    bot = "bot"
