"""Transactions and the review/dedup/rule tables built around them."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import (
    Direction,
    DuplicateMatchType,
    DuplicateStatus,
    ResolvedAction,
    ReviewIssueType,
    ReviewItemStatus,
    ReviewStatus,
    TransactionType,
)
from app.models.mixins import CreatedAtMixin, TimestampMixin, enum_column


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    # Nullable FKs: a transaction may be entered manually (no document/account)
    # and is enriched with category/vendor/customer later during review.
    document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_date: Mapped[Optional[date]] = mapped_column(Date)
    description_raw: Mapped[Optional[str]] = mapped_column(String(1024))
    description_clean: Mapped[Optional[str]] = mapped_column(String(1024))
    merchant_name: Mapped[Optional[str]] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    direction: Mapped[Direction] = enum_column(Direction, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"))
    transaction_type: Mapped[TransactionType] = enum_column(
        TransactionType, default=TransactionType.unknown, nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column()
    review_status: Mapped[ReviewStatus] = enum_column(
        ReviewStatus, default=ReviewStatus.needs_review, nullable=False
    )
    # Stable hash of the economic identity of a row — the basis for dedup.
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    is_excluded_from_pnl: Mapped[bool] = mapped_column(default=False, nullable=False)
    exclusion_reason: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    business: Mapped["Business"] = relationship(back_populates="transactions")
    document: Mapped[Optional["Document"]] = relationship(back_populates="transactions")
    account: Mapped[Optional["Account"]] = relationship(back_populates="transactions")
    category: Mapped[Optional["Category"]] = relationship(back_populates="transactions")
    vendor: Mapped[Optional["Vendor"]] = relationship(back_populates="transactions")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="transactions")


class DuplicateCandidate(Base, CreatedAtMixin):
    __tablename__ = "duplicate_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    transaction_id_1: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    transaction_id_2: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    match_type: Mapped[DuplicateMatchType] = enum_column(
        DuplicateMatchType, nullable=False
    )
    match_score: Mapped[Optional[float]] = mapped_column()
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[DuplicateStatus] = enum_column(
        DuplicateStatus, default=DuplicateStatus.pending_review, nullable=False
    )
    resolved_action: Mapped[Optional[ResolvedAction]] = enum_column(ResolvedAction)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Two FKs point at the same table, so SQLAlchemy needs `foreign_keys` to
    # tell the relationships apart.
    transaction_1: Mapped["Transaction"] = relationship(
        foreign_keys=[transaction_id_1]
    )
    transaction_2: Mapped["Transaction"] = relationship(
        foreign_keys=[transaction_id_2]
    )


class ReviewItem(Base, CreatedAtMixin):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    issue_type: Mapped[ReviewIssueType] = enum_column(ReviewIssueType, nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    suggested_action: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReviewItemStatus] = enum_column(
        ReviewItemStatus, default=ReviewItemStatus.open, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    transaction: Mapped[Optional["Transaction"]] = relationship()


class CategorizationRule(Base, CreatedAtMixin):
    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    merchant_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    transaction_type: Mapped[Optional[TransactionType]] = enum_column(TransactionType)
    confidence_boost: Mapped[Optional[float]] = mapped_column()

    category: Mapped[Optional["Category"]] = relationship()


# Resolve forward references used in the relationships above at runtime.
from app.models.business import (  # noqa: E402,F401
    Account,
    Business,
    Category,
    Customer,
    Vendor,
)
from app.models.document import Document  # noqa: E402,F401
