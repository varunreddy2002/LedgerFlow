"""SQLAlchemy ORM models for the double-entry ledger core.

These seven tables replace the old flat ``transactions`` world:

* :class:`Account`            — the chart of accounts (3-level tree, posting only at leaves).
* :class:`JournalEntry`       — journal-entry header (the proposal *is* a DRAFT header).
* :class:`JournalEntryLine`   — the debit/credit lines; the heart of double-entry.
* :class:`BankTransaction`    — raw imported bank rows that feed the escalation ladder.
* :class:`AccountingRule`     — deterministic + learned classification rules (JSONB).
* :class:`ApprovalEvent`      — audit trail of every human/rule approval decision.
* :class:`ReviewItem`         — the unified exception queue.

Invariants that must hold in code (some also enforced as DB CHECKs):

* a line carries a debit *or* a credit, never both, never neither;
* only :attr:`Account.posting_allowed` (level-3 leaf) accounts may be referenced by a line;
* a POSTED journal entry has ``Σ debit == Σ credit``.

The sign convention itself lives once in
:mod:`app.application.accounting.ledger`; models only store the raw amounts.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AccountType,
    ApprovalDecision,
    BankTxnStatus,
    EscalationSource,
    JournalEntryStatus,
    JournalType,
    NormalBalance,
    ReviewItemType,
    ReviewStatus,
    TxnEventType,
)
from app.domain.models.mixins import (
    CreatedAtMixin,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_column,
)
from app.infrastructure.db.database import Base

# Money uses two-decimal fixed precision everywhere; declared once for DRY.
_MONEY = Numeric(14, 2)


class Account(Base, PrimaryKeyMixin, TimestampMixin):
    """A chart-of-accounts node.

    The COA is a 3-level tree: level 1 = account type header (``1000 Assets``),
    level 2 = reporting group (``1100 Cash``), level 3 = posting leaf
    (``1110 Operating Checking``). Journal entry lines may reference **only**
    posting leaves (``posting_allowed=True``); reports roll leaf balances up the
    ``parent_account_id`` chain.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("business_id", "account_code", name="uq_accounts_business_code"),
        Index("ix_accounts_business_parent", "business_id", "parent_account_id"),
        Index("ix_accounts_business_type", "business_id", "account_type"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    account_code: Mapped[str] = mapped_column(String(10), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[AccountType] = enum_column(AccountType, nullable=False)
    account_subtype: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parent_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    hierarchy_level: Mapped[int] = mapped_column(SmallInteger, default=3, nullable=False)
    normal_balance: Mapped[NormalBalance] = enum_column(NormalBalance, nullable=False)
    posting_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_control_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="accounts")
    parent: Mapped[Optional["Account"]] = relationship(
        back_populates="children", remote_side="Account.id"
    )
    children: Mapped[List["Account"]] = relationship(back_populates="parent")
    lines: Mapped[List["JournalEntryLine"]] = relationship(back_populates="account")


class JournalEntry(Base, PrimaryKeyMixin, TimestampMixin):
    """Journal-entry header. A DRAFT/PENDING_APPROVAL header *is* the proposal;
    approval flips it to POSTED. Only POSTED entries are visible to reports."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_biz_status_date", "business_id", "status", "entry_date"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    journal_type: Mapped[JournalType] = enum_column(
        JournalType, default=JournalType.GENERAL, nullable=False
    )
    entry_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    event_type: Mapped[TxnEventType] = enum_column(
        TxnEventType, default=TxnEventType.MANUAL, nullable=False
    )
    status: Mapped[JournalEntryStatus] = enum_column(
        JournalEntryStatus, default=JournalEntryStatus.DRAFT, nullable=False
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Set when the escalation ladder (rule/agent) drafted this entry; null = manual/human.
    source: Mapped[Optional[EscalationSource]] = enum_column(EscalationSource, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    reverses_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True
    )

    lines: Mapped[List["JournalEntryLine"]] = relationship(
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.sequence_number",
    )


class JournalEntryLine(Base, PrimaryKeyMixin, CreatedAtMixin):
    """A single debit or credit line. Immutable once its entry is POSTED, hence
    :class:`CreatedAtMixin` (no ``updated_at``)."""

    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="ck_jel_debit_nonneg"),
        CheckConstraint("credit_amount >= 0", name="ck_jel_credit_nonneg"),
        CheckConstraint(
            "NOT (debit_amount > 0 AND credit_amount > 0)", name="ck_jel_one_side"
        ),
        CheckConstraint(
            "debit_amount > 0 OR credit_amount > 0", name="ck_jel_nonempty"
        ),
        Index("ix_jel_account", "account_id"),
        Index("ix_jel_journal_entry", "journal_entry_id"),
    )

    journal_entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"), nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    reason_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    journal_entry: Mapped["JournalEntry"] = relationship(back_populates="lines")
    account: Mapped["Account"] = relationship(back_populates="lines")


class BankTransaction(Base, PrimaryKeyMixin, TimestampMixin):
    """A raw imported bank row — the source that feeds the escalation ladder.

    ``cash_movement`` expresses the direction in double-entry terms: ``DEBIT``
    means the cash (asset) account increased (a deposit); ``CREDIT`` means it
    decreased (a payment). ``amount`` is always positive.
    """

    __tablename__ = "bank_transactions"
    __table_args__ = (
        Index("ix_bank_txn_biz_status", "business_id", "status"),
        Index("ix_bank_txn_fingerprint", "fingerprint_hash"),
        Index("ix_bank_txn_external", "gl_account_id", "external_transaction_id"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    # The ASSET account this bank statement belongs to (e.g. 1110 Operating Checking).
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # The posted journal entry once the row has been categorized and approved.
    journal_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True
    )
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    normalized_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    cash_movement: Mapped[NormalBalance] = enum_column(NormalBalance, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[BankTxnStatus] = enum_column(
        BankTxnStatus, default=BankTxnStatus.UNPROCESSED, nullable=False
    )


class AccountingRule(Base, PrimaryKeyMixin, TimestampMixin):
    """A classification rule: match ``conditions`` on a source row, apply
    ``actions`` (pick an account + confidence). Seeded rules are ``is_system``;
    rules born from human corrections are the learned-memory flywheel."""

    __tablename__ = "accounting_rules"
    __table_args__ = (
        Index("ix_accounting_rules_biz_active_priority", "business_id", "is_active", "priority"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=100, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalEvent(Base, PrimaryKeyMixin, CreatedAtMixin):
    """Immutable audit record of a decision on a draft JE or a review item.

    Exactly one of :attr:`journal_entry_id` / :attr:`review_item_id` is set,
    depending on what was decided."""

    __tablename__ = "approval_events"

    journal_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_entries.id"), index=True, nullable=True
    )
    review_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("review_items.id"), index=True, nullable=True
    )
    decision: Mapped[ApprovalDecision] = enum_column(ApprovalDecision, nullable=False)
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ReviewItem(Base, PrimaryKeyMixin, TimestampMixin):
    """A single entry in the unified exception queue.

    Polymorphic by (``subject_type``, ``subject_id``) so any source row can be
    parked for review without a bespoke table per gap type. ``proposed_resolution``
    carries the rule/agent's best guess (e.g. the account_id it would post to);
    the human confirms, corrects, or dismisses it.
    """

    __tablename__ = "review_items"
    __table_args__ = (
        Index("ix_review_items_biz_status_type", "business_id", "status", "item_type"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    item_type: Mapped[ReviewItemType] = enum_column(ReviewItemType, nullable=False)
    status: Mapped[ReviewStatus] = enum_column(
        ReviewStatus, default=ReviewStatus.OPEN, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[EscalationSource] = enum_column(EscalationSource, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposed_resolution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    decision: Mapped[Optional[ApprovalDecision]] = enum_column(ApprovalDecision, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


from app.domain.models.business import Business  # noqa: E402,F401
from app.domain.models.document import Document  # noqa: E402,F401
