"""Enumerations shared across the LedgerFlow domain.

All enums are `StrEnum` so their `.value` is a stable, human-readable string.
They are persisted as ``VARCHAR + CHECK`` via :func:`app.domain.models.mixins.enum_column`,
which keeps rows readable and portable across Postgres/SQLite.

The ledger-core enums (accounting_schema.md §0) replace the old flat-transaction
vocabulary: `AccountType` now describes chart-of-accounts classification
(asset/liability/…) rather than bank-account kinds, and cash movement is expressed
in true double-entry terms via `NormalBalance` — there is deliberately no
INFLOW/OUTFLOW concept anywhere in the system.
"""

from enum import StrEnum


# ── Document ingestion (kept from the prior schema) ────────────────────────
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


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


# ── Ledger core ────────────────────────────────────────────────────────────
class AccountType(StrEnum):
    """Chart-of-accounts classification. Drives which statement an account
    rolls up into and its :class:`NormalBalance`."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(StrEnum):
    """The side on which an account's balance normally sits.

    Assets and expenses are debit-normal; liabilities, equity and revenue are
    credit-normal. This is the single fact from which every sign rule derives.
    """

    DEBIT = "debit"
    CREDIT = "credit"


class JournalType(StrEnum):
    """Sub-journal a journal entry belongs to (all GENERAL)."""

    GENERAL = "general"
    SALES = "sales"
    PURCHASE = "purchase"
    BANK = "bank"
    ADJUSTMENT = "adjustment"


class TxnEventType(StrEnum):
    """The real-world event a journal entry represents."""

    BILL = "bill"
    INVOICE = "invoice"
    PAYMENT = "payment"
    ADJUSTMENT = "adjustment"
    OPENING_BALANCE = "opening_balance"
    MANUAL = "manual"


class JournalEntryStatus(StrEnum):
    """Lifecycle of a journal entry. Only POSTED entries count in reports.

    A DRAFT/PENDING_APPROVAL entry is the *proposal* awaiting the human gate;
    approval flips it to POSTED. REVERSED marks an entry undone by a contra JE.
    """

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    POSTED = "posted"
    REVERSED = "reversed"


class BankTxnStatus(StrEnum):
    """Lifecycle of a raw imported bank row as it feeds the escalation ladder."""

    UNPROCESSED = "unprocessed"
    PROPOSED = "proposed"
    POSTED = "posted"
    EXCLUDED = "excluded"


class ApprovalDecision(StrEnum):
    """Outcome recorded on an approval event / resolved review item."""

    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


# ── Review / exception queue ───────────────────────────────────────────────
class ReviewItemType(StrEnum):
    """The kind of exception a review item represents.

    Only ``UNCATEGORIZED`` and ``LARGE_AMOUNT`` are fully handled; 
    TO-DO: the remaining members are registered as stubs so the queue is generic and new
    types slot in without touching the dispatch mechanism.
    """

    UNCATEGORIZED = "uncategorized"
    UNMATCHED_PARTY = "unmatched_party"
    DUPLICATE = "duplicate"
    UNBALANCED = "unbalanced"
    NEW_ACCOUNT = "new_account"
    LARGE_AMOUNT = "large_amount"
    LOW_EXTRACTION = "low_extraction"
    AMBIGUOUS_DOC = "ambiguous_doc"
    PAYMENT_MATCH = "payment_match"


class ReviewStatus(StrEnum):
    """Lifecycle of a review item in the unified exception queue."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class EscalationSource(StrEnum):
    """Which layer of the escalation ladder produced a proposal / review item."""

    RULE = "rule"
    AGENT = "agent"
