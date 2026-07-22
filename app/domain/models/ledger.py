"""Domain models for the double-entry ledger core.

Starting with the chart of accounts (``Account``) — the foundation every other
ledger table (journal entries, bank transactions, accounting rules) will
reference by FK. More tables land in this module as the rebuild progresses.
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
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import (
    ActorMixin,
    CreatedAtMixin,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_column,
)
from app.domain.enums import (
    AccountType,
    AuditActorType,
    AuditEventType,
    BankTxnStatus,
    CashDirection,
    InvoiceBillStatus,
    NormalBalance,
    RuleStatus,
    TransactionStatus,
)

# Money uses two-decimal fixed precision everywhere; declared once for DRY.
_MONEY = Numeric(14, 2)


class Account(Base, PrimaryKeyMixin, TimestampMixin, ActorMixin):
    """A chart-of-accounts node.

    Fixed 3-level tree: level 1 = type header (``1000 Assets``), level 2 =
    reporting group (``1100 Cash and Bank``), level 3 = posting leaf
    (``1110 Operating Checking``). Journal entry lines may only reference
    leaves (``posting_allowed=True``) — levels 1-2 exist purely for
    rollup/reporting, never posted to directly.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("business_id", "account_code", name="uq_accounts_business_code"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    account_code: Mapped[str] = mapped_column(String(10), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[AccountType] = enum_column(AccountType, nullable=False)
    # Functional role tag (e.g. "cash", "equity") — free text, not an enum, so new
    # subtypes don't require a migration. Declared on level-2 groups, read by leaves.
    account_subtype: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parent_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    hierarchy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Stored, not derived from account_type, so contra accounts (e.g. Owner Draws)
    # can override the type's default without special-casing them elsewhere.
    normal_balance: Mapped[NormalBalance] = enum_column(NormalBalance, nullable=False)
    posting_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="accounts")
    parent: Mapped[Optional["Account"]] = relationship(
        back_populates="children", remote_side="Account.id"
    )
    children: Mapped[List["Account"]] = relationship(back_populates="parent")


class BankTransaction(Base, PrimaryKeyMixin, TimestampMixin):
    """A raw row extracted from a bank statement — source evidence, not yet an
    accounting interpretation. ``account_id`` is the cash/bank leaf in the COA
    this row belongs to (e.g. 1110 Operating Checking); ``amount`` stays
    positive, ``direction`` carries which way cash moved."""

    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "fingerprint_hash", name="uq_bank_transactions_business_fingerprint"
        ),
    )

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    normalized_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    direction: Mapped[CashDirection] = enum_column(CashDirection, nullable=False)
    # sha256(business_id:account_id:transaction_date:amount:normalized_description) —
    # row-level dedup for overlapping statement periods (file-level checksum on
    # Document only catches re-uploading the identical file, not overlap).
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[BankTxnStatus] = enum_column(
        BankTxnStatus, default=BankTxnStatus.NEW, nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="bank_transactions")
    account: Mapped["Account"] = relationship()


class Transaction(Base, PrimaryKeyMixin, TimestampMixin, ActorMixin):
    """The accounting event header — 'AWS payment', 'Customer payment received'.
    Carries no account-level amounts itself; those live on TransactionEntry.
    Review state (status/confidence/reviewed_by) lives directly on this row —
    no separate review-queue table for the MVP, per the design doc."""

    __tablename__ = "transactions"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    bank_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bank_transactions.id"), nullable=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[TransactionStatus] = enum_column(
        TransactionStatus, default=TransactionStatus.PROPOSED, nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="transactions")
    bank_transaction: Mapped[Optional["BankTransaction"]] = relationship()
    entries: Mapped[List["TransactionEntry"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class TransactionEntry(Base, PrimaryKeyMixin, CreatedAtMixin):
    """One debit or credit line inside a transaction. ``amount`` is signed:
    positive = debit, negative = credit (design doc section 10) — the opposite
    convention from a two-column debit/credit split. No updated_at/updated_by:
    entries are immutable once written; corrections are reversal transactions."""

    __tablename__ = "transaction_entries"
    __table_args__ = (
        CheckConstraint("amount != 0", name="ck_transaction_entries_amount_nonzero"),
    )

    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship()


class AccountingRule(Base, PrimaryKeyMixin, TimestampMixin, ActorMixin):
    """A deterministic classification rule: match ``conditions`` on a bank row,
    apply ``actions`` (pick an account + confidence)."""

    __tablename__ = "accounting_rules"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=100, nullable=False)
    status: Mapped[RuleStatus] = enum_column(RuleStatus, default=RuleStatus.ACTIVE, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="accounting_rules")


class AuditEvent(Base, PrimaryKeyMixin, CreatedAtMixin):
    """Append-only audit trail. Polymorphic by (entity_type, entity_id) so any
    table can be audited without a bespoke audit table per entity. No
    updated_at/updated_by — audit rows are never modified after creation."""

    __tablename__ = "audit_events"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # No FK — polymorphic by entity_type. Explicit BigInteger since it points at
    # BigInteger PKs on other tables and a bare Mapped[int] would default to Integer.
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[AuditEventType] = enum_column(AuditEventType, nullable=False)
    actor_type: Mapped[AuditActorType] = enum_column(AuditActorType, nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    business: Mapped["Business"] = relationship()


class Invoice(Base, PrimaryKeyMixin, TimestampMixin, ActorMixin):
    """A customer invoice. Cash-basis rule: creating this does NOT create
    revenue — that happens only when bank_transaction_id gets linked to an
    actual payment and accounting_transaction_id points at the resulting
    Transaction."""

    __tablename__ = "invoices"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[InvoiceBillStatus] = enum_column(
        InvoiceBillStatus, default=InvoiceBillStatus.DRAFT, nullable=False
    )
    bank_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bank_transactions.id"), nullable=True
    )
    accounting_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )

    business: Mapped["Business"] = relationship(back_populates="invoices")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="invoices")
    lines: Mapped[List["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base, PrimaryKeyMixin, TimestampMixin):
    """line_amount/subtotal/tax/total are derived via query (quantity *
    unit_price, summed), not stored — per the design doc."""

    __tablename__ = "invoice_lines"

    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("1"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"), nullable=False)
    revenue_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")
    revenue_account: Mapped[Optional["Account"]] = relationship()


class Bill(Base, PrimaryKeyMixin, TimestampMixin, ActorMixin):
    """A vendor bill. Cash-basis rule: receiving this does NOT create an
    expense — that happens only when linked to an actual payment."""

    __tablename__ = "bills"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    bill_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[InvoiceBillStatus] = enum_column(
        InvoiceBillStatus, default=InvoiceBillStatus.DRAFT, nullable=False
    )
    bank_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bank_transactions.id"), nullable=True
    )
    accounting_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )

    business: Mapped["Business"] = relationship(back_populates="bills")
    vendor: Mapped[Optional["Vendor"]] = relationship(back_populates="bills")
    lines: Mapped[List["BillLine"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )


class BillLine(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bill_lines"

    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("1"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"), nullable=False)
    expense_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)

    bill: Mapped["Bill"] = relationship(back_populates="lines")
    expense_account: Mapped[Optional["Account"]] = relationship()


from app.domain.models.business import Business, Customer, Vendor  # noqa: E402,F401
