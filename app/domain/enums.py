from enum import StrEnum


class SourceType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    CREDIT_CARD = "credit_card"
    VENDOR_BILL = "vendor_bill"
    INVOICE = "invoice"
    UNKNOWN = "unknown"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class AccountType(StrEnum):
    """Top-level chart-of-accounts type. Equity is not its own type here —
    it lives under LIABILITY via account_subtype='equity' (see ledger.py)."""

    ASSET = "asset"
    LIABILITY = "liability"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(StrEnum):
    """Which side (debit/credit) increases an account's balance."""

    DEBIT = "debit"
    CREDIT = "credit"


class BankTxnStatus(StrEnum):
    """Lifecycle of a bank_transactions row through the classification pipeline."""

    NEW = "new"
    PROCESSING = "processing"
    REVIEW_REQUIRED = "review_required"
    PROCESSED = "processed"
    EXCLUDED = "excluded"
    FAILED = "failed"


class CashDirection(StrEnum):
    """Which way cash moved on a bank_transactions row."""

    INFLOW = "inflow"
    OUTFLOW = "outflow"


class TransactionStatus(StrEnum):
    """Lifecycle of an accounting transaction (the journal header)."""

    PROPOSED = "proposed"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    REVERSED = "reversed"
    FAILED = "failed"


class InvoiceBillStatus(StrEnum):
    """Shared lifecycle for invoices and bills.

    REVIEW_REQUIRED added post-rebuild (not in the original design doc's value
    set): set when ingestion can't fully trust the extraction — an unresolved
    vendor/customer, or zero line items — so a human confirms before this can
    be reconciled against a payment. Mirrors BankTxnStatus/TransactionStatus's
    existing REVIEW_REQUIRED, kept off DocumentStatus since Document only
    tracks file-processing outcome, not financial-record trustworthiness.
    """

    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    UNPAID = "unpaid"
    PAID = "paid"
    VOID = "void"


class RuleStatus(StrEnum):
    """Not specified explicitly in the design doc's accounting_rules table —
    this is a judgment call, flag if you want something different."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class PartyStatus(StrEnum):
    """Not specified explicitly in the design doc's customers/vendors tables —
    a judgment call, same as RuleStatus."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class AuditActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    RULE_ENGINE = "rule_engine"


class AuditEventType(StrEnum):
    CREATED = "created"
    EXTRACTED = "extracted"
    CLASSIFIED = "classified"
    MODIFIED = "modified"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    REVERSED = "reversed"
    RECONCILED = "reconciled"
    FAILED = "failed"


class CategoryType(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    OWNER_DRAW = "owner_draw"


class TransactionType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class ReviewStatus(StrEnum):
    UNCATEGORIZED = "uncategorized"
    NEEDS_REVIEW = "needs_review"
    AUTO_APPROVED = "auto_approved"
    USER_APPROVED = "user_approved"
    USER_CORRECTED = "user_corrected"
    IGNORED = "ignored"

class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
