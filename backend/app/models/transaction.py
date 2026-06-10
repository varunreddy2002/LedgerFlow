"""Transactions and the review / dedup / rule tables built around them."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import (
    Direction,
    DuplicateGroupStatus,
    DuplicateMatchType,
    DuplicateResolution,
    ReviewIssueType,
    ReviewItemStatus,
    ReviewStatus,
    TransactionType,
)
from app.models.mixins import CreatedAtMixin, PrimaryKeyMixin, TimestampMixin, enum_column


class Transaction(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"

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
    merchant_name: Mapped[Optional[str]] = mapped_column(String(150))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    direction: Mapped[Direction] = enum_column(Direction, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"))
    transaction_type: Mapped[TransactionType] = enum_column(
        TransactionType, default=TransactionType.UNKNOWN, nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column()
    review_status: Mapped[ReviewStatus] = enum_column(
        ReviewStatus, default=ReviewStatus.NEEDS_REVIEW, nullable=False
    )
    # Stable hash of the economic identity of a row — the basis for dedup.
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    is_excluded_from_pnl: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    exclusion_reason: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    business: Mapped["Business"] = relationship(back_populates="transactions")
    document: Mapped[Optional["Document"]] = relationship(back_populates="transactions")
    account: Mapped[Optional["Account"]] = relationship(back_populates="transactions")
    category: Mapped[Optional["Category"]] = relationship(back_populates="transactions")
    vendor: Mapped[Optional["Vendor"]] = relationship(back_populates="transactions")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="transactions")
    duplicate_memberships: Mapped[List["DuplicateGroupMember"]] = relationship(
        back_populates="transaction"
    )


# ---------------------------------------------------------------------------
# Duplicate detection — group-based design supports 2+ duplicates cleanly
# ---------------------------------------------------------------------------

class DuplicateGroup(Base, PrimaryKeyMixin, TimestampMixin):
    """One row per cluster of duplicate transactions sharing the same fingerprint.

    All transactions suspected to be the same economic event are linked via
    DuplicateGroupMember.  The reviewer resolves the group once and the
    resolution (keep_one / keep_all / exclude_all) is applied to each member.
    """

    __tablename__ = "duplicate_groups"

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    match_type: Mapped[DuplicateMatchType] = enum_column(
        DuplicateMatchType, nullable=False
    )
    match_score: Mapped[Optional[float]] = mapped_column()   # 1.0 for exact, <1 for fuzzy
    status: Mapped[DuplicateGroupStatus] = enum_column(
        DuplicateGroupStatus,
        default=DuplicateGroupStatus.PENDING_REVIEW,
        nullable=False,
    )
    resolution: Mapped[Optional[DuplicateResolution]] = enum_column(
        DuplicateResolution
    )  # null until resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    members: Mapped[List["DuplicateGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    resolved_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[resolved_by_user_id]
    )


class DuplicateGroupMember(Base, PrimaryKeyMixin, CreatedAtMixin):
    """Junction table: one row per transaction per duplicate group.

    A transaction can belong to at most one group (enforced by unique constraint
    on transaction_id).  ``is_primary`` marks the first / canonical transaction.
    ``is_kept`` is null until the group is resolved, then set to true/false per
    member to drive is_excluded_from_pnl on the linked transaction.
    """

    __tablename__ = "duplicate_group_members"
    __table_args__ = (
        # A transaction can only be in one duplicate group.
        UniqueConstraint("transaction_id", name="uq_member_transaction"),
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("duplicate_groups.id"), index=True, nullable=False
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), index=True, nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # True for the first/canonical transaction in the group
    is_kept: Mapped[Optional[bool]] = mapped_column(
        Boolean
    )  # null=unresolved, True=keep in P&L, False=exclude

    group: Mapped["DuplicateGroup"] = relationship(back_populates="members")
    transaction: Mapped["Transaction"] = relationship(
        back_populates="duplicate_memberships"
    )


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

class ReviewItem(Base, PrimaryKeyMixin, CreatedAtMixin):
    """One flagged issue per transaction or duplicate group awaiting human review."""

    __tablename__ = "review_items"

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    # transaction_id is set for all issue types.
    # duplicate_group_id is additionally set when issue_type = POSSIBLE_DUPLICATE.
    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    duplicate_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("duplicate_groups.id"), index=True
    )
    issue_type: Mapped[ReviewIssueType] = enum_column(ReviewIssueType, nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    suggested_action: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReviewItemStatus] = enum_column(
        ReviewItemStatus, default=ReviewItemStatus.OPEN, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    transaction: Mapped[Optional["Transaction"]] = relationship()
    duplicate_group: Mapped[Optional["DuplicateGroup"]] = relationship()
    resolved_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[resolved_by_user_id]
    )


# ---------------------------------------------------------------------------
# Categorization rules
# ---------------------------------------------------------------------------

class CategorizationRule(Base, PrimaryKeyMixin, CreatedAtMixin):
    """Regex-based rules that auto-assign categories during CSV import.

    The categorization engine loads all rules for a business (TTL-cached),
    matches ``merchant_pattern`` against ``Transaction.description_raw``, and
    assigns ``category_id`` / ``transaction_type`` with ``confidence_boost``
    as the confidence score (0.0–1.0).  Null confidence_boost defaults to 0.85.
    """

    __tablename__ = "categorization_rules"

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    # Regex pattern matched against description_raw (case-insensitive).
    # 500 chars to accommodate complex patterns.
    merchant_pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    transaction_type: Mapped[Optional[TransactionType]] = enum_column(TransactionType)
    # Treated as the direct confidence score (0.0–1.0), not an additive boost.
    # Null → engine defaults to 0.85.
    confidence_boost: Mapped[Optional[float]] = mapped_column()

    category: Mapped[Optional["Category"]] = relationship()


# ---------------------------------------------------------------------------
# Resolve forward references used in relationships above.
# ---------------------------------------------------------------------------
from app.models.business import (  # noqa: E402,F401
    Account,
    Business,
    Category,
    Customer,
    Vendor,
)
from app.models.document import Document  # noqa: E402,F401
from app.models.user import User          # noqa: E402,F401
