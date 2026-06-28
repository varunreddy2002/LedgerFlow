from enum import StrEnum


class SourceType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    CREDIT_CARD = "credit_card"
    VENDOR_BILL = "vendor_bill"
    INVOICE = "invoice"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    OTHER = "other"


class CategoryType(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    OWNER_DRAW = "owner_draw"


class TransactionType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    AUTO_APPROVED = "auto_approved"
    USER_APPROVED = "user_approved"
    USER_CORRECTED = "user_corrected"
    IGNORED = "ignored"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
