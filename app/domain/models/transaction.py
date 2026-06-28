from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import CreatedAtMixin, PrimaryKeyMixin, TimestampMixin, enum_column
from app.domain.enums import ReviewStatus, TransactionType


class Transaction(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"

    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), index=True, nullable=True)
    party_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    trans_type: Mapped[TransactionType] = enum_column(TransactionType, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    review_status: Mapped[ReviewStatus] = enum_column(ReviewStatus, default=ReviewStatus.NEEDS_REVIEW, nullable=False)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    document: Mapped[Optional["Document"]] = relationship(back_populates="transactions")
    vendor: Mapped[Optional["Vendor"]] = relationship(back_populates="transactions")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="transactions")
    category: Mapped[Optional["Category"]] = relationship(back_populates="transactions")
    line_items: Mapped[List["TransactionLineItem"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")


class TransactionLineItem(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "transaction_line_items"

    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    review_status: Mapped[ReviewStatus] = enum_column(ReviewStatus, default=ReviewStatus.NEEDS_REVIEW, nullable=False)

    transaction: Mapped["Transaction"] = relationship(back_populates="line_items")
    category: Mapped[Optional["Category"]] = relationship()


class CategorizationRule(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categorization_rules"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    match_field: Mapped[str] = mapped_column(String(50), default="description", nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[Optional["Category"]] = relationship()


from app.domain.models.business import Business, Category, Customer, Vendor  # noqa: E402,F401
from app.domain.models.document import Document  # noqa: E402,F401
