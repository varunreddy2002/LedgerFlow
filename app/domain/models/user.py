"""Application users — one user belongs to one business (multi-tenant auth later)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base
from app.domain.models.mixins import PrimaryKeyMixin, TimestampMixin


class User(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # One email per business (different businesses can share an email later
        # when we add cross-business auth, but scoped per business for now).
        UniqueConstraint("business_id", "email", name="uq_user_business_email"),
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Password hash and auth tokens are added when auth is implemented.

    business: Mapped["Business"] = relationship()


# Forward reference — resolved at runtime via models/__init__.py import order.
from app.domain.models.business import Business  # noqa: E402,F401
