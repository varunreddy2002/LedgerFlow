from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.db.database import Base
from app.domain.models.mixins import CreatedAtMixin, PrimaryKeyMixin, TimestampMixin, enum_column
from app.domain.enums import ChatRole


class ChatSession(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chat_sessions"

    thread_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), nullable=False, unique=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(200))

    messages: Mapped[List["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "chat_messages"

    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True, nullable=False)
    role: Mapped[ChatRole] = enum_column(ChatRole, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


from app.domain.models.user import User  # noqa: E402,F401
