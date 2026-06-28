from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.db.database import Base
from app.domain.models.mixins import CreatedAtMixin, PrimaryKeyMixin


class AuditLog(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "audit_logs"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)

    business: Mapped["Business"] = relationship()
    user: Mapped[Optional["User"]] = relationship()


from app.domain.models.business import Business  # noqa: E402,F401
from app.domain.models.user import User  # noqa: E402,F401
