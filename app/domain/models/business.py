from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import PrimaryKeyMixin, TimestampMixin, enum_column
from app.domain.enums import PartyStatus


class Business(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    documents: Mapped[List["Document"]] = relationship(back_populates="business")
    accounts: Mapped[List["Account"]] = relationship(back_populates="business")
    vendors: Mapped[List["Vendor"]] = relationship(back_populates="business")
    customers: Mapped[List["Customer"]] = relationship(back_populates="business")
    bank_transactions: Mapped[List["BankTransaction"]] = relationship(back_populates="business")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="business")
    accounting_rules: Mapped[List["AccountingRule"]] = relationship(back_populates="business")
    invoices: Mapped[List["Invoice"]] = relationship(back_populates="business")
    bills: Mapped[List["Bill"]] = relationship(back_populates="business")


class Vendor(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendors"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Recurring-classification hint (e.g. AWS -> Cloud Hosting Expense). Points at
    # a posting leaf in the COA; nullable until a pattern is actually learned.
    default_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    status: Mapped[PartyStatus] = enum_column(PartyStatus, default=PartyStatus.ACTIVE, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="vendors")
    default_account: Mapped[Optional["Account"]] = relationship()
    bills: Mapped[List["Bill"]] = relationship(back_populates="vendor")


class Customer(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status: Mapped[PartyStatus] = enum_column(PartyStatus, default=PartyStatus.ACTIVE, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="customers")
    invoices: Mapped[List["Invoice"]] = relationship(back_populates="customer")


from app.domain.models.document import Document  # noqa: E402,F401
from app.domain.models.ledger import (  # noqa: E402,F401
    Account, BankTransaction, Transaction, AccountingRule, Invoice, Bill,
)
