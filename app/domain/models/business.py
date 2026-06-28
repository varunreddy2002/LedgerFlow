from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import CreatedAtMixin, PrimaryKeyMixin, TimestampMixin, enum_column
from app.domain.enums import AccountType, CategoryType


class Business(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    documents: Mapped[List["Document"]] = relationship(back_populates="business")
    accounts: Mapped[List["Account"]] = relationship(back_populates="business")
    categories: Mapped[List["Category"]] = relationship(back_populates="business")
    vendors: Mapped[List["Vendor"]] = relationship(back_populates="business")
    customers: Mapped[List["Customer"]] = relationship(back_populates="business")


class Account(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_type: Mapped[AccountType] = enum_column(AccountType, nullable=False)
    institution_name: Mapped[Optional[str]] = mapped_column(String(150))
    last_four: Mapped[Optional[str]] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    business: Mapped["Business"] = relationship(back_populates="accounts")


class Category(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    category_type: Mapped[CategoryType] = enum_column(CategoryType, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="categories")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="category")
    parent: Mapped[Optional["Category"]] = relationship(back_populates="children", remote_side="Category.id")
    children: Mapped[List["Category"]] = relationship(back_populates="parent")


class Vendor(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendors"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    business: Mapped["Business"] = relationship(back_populates="vendors")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="vendor")


class Customer(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    business: Mapped["Business"] = relationship(back_populates="customers")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="customer")


from app.domain.models.document import Document  # noqa: E402,F401
from app.domain.models.transaction import Transaction  # noqa: E402,F401
