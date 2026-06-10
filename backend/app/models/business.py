"""Business and its owned lookup entities: accounts, categories, vendors, customers."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import AccountType, CategoryType
from app.models.mixins import CreatedAtMixin, TimestampMixin, enum_column


class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # Collections — the "one" side of each one-to-many owned by a business.
    documents: Mapped[List["Document"]] = relationship(back_populates="business")
    accounts: Mapped[List["Account"]] = relationship(back_populates="business")
    categories: Mapped[List["Category"]] = relationship(back_populates="business")
    vendors: Mapped[List["Vendor"]] = relationship(back_populates="business")
    customers: Mapped[List["Customer"]] = relationship(back_populates="business")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="business")


class Account(Base, CreatedAtMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = enum_column(AccountType, nullable=False)
    institution_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_four: Mapped[Optional[str]] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    business: Mapped["Business"] = relationship(back_populates="accounts")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="account")


class Category(Base, CreatedAtMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Self-referential parent: a category may sit under another category of the
    # same business, forming a tree (e.g. "Figma" under "Software Subscriptions").
    parent_category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id")
    )
    category_type: Mapped[CategoryType] = enum_column(CategoryType, nullable=False)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="categories")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="category")
    # `remote_side=[id]` marks the "one" end so SQLAlchemy knows this FK points
    # back up to a parent row in the same table.
    parent: Mapped[Optional["Category"]] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[List["Category"]] = relationship(back_populates="parent")


class Vendor(Base, CreatedAtMixin):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    default_category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id")
    )
    vendor_type: Mapped[Optional[str]] = mapped_column(String(100))

    business: Mapped["Business"] = relationship(back_populates="vendors")
    default_category: Mapped[Optional["Category"]] = relationship()
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="vendor")


class Customer(Base, CreatedAtMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    source: Mapped[Optional[str]] = mapped_column(String(100))

    business: Mapped["Business"] = relationship(back_populates="customers")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="customer")


# Imported lazily by SQLAlchemy's registry via string names above; the explicit
# import here is only to satisfy type checkers / forward references at runtime.
from app.models.document import Document  # noqa: E402,F401
from app.models.transaction import Transaction  # noqa: E402,F401
