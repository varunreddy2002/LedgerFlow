"""Tenant + party models.

The old bank ``Account`` and ``Category`` tables were retired: bank accounts are
now ASSET rows in the chart of accounts (:class:`app.domain.models.ledger.Account`)
and categories became the full COA. What remains here is the tenant
(:class:`Business`) and the two party tables (:class:`Vendor` / :class:`Customer`)
that ingestion and party-matching upsert into.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import PrimaryKeyMixin, TimestampMixin


class Business(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    documents: Mapped[List["Document"]] = relationship(back_populates="business")
    accounts: Mapped[List["Account"]] = relationship(back_populates="business")
    vendors: Mapped[List["Vendor"]] = relationship(back_populates="business")
    customers: Mapped[List["Customer"]] = relationship(back_populates="business")


class Vendor(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendors"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="vendors")


class Customer(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="customers")


from app.domain.models.document import Document  # noqa: E402,F401
from app.domain.models.ledger import Account  # noqa: E402,F401
