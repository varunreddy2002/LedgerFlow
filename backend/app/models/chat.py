"""Assistant chat sessions and their messages."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.models.enums import ChatRole
from app.models.mixins import CreatedAtMixin, PrimaryKeyMixin, enum_column


class ChatSession(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "chat_sessions"

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(200))

    business: Mapped["Business"] = relationship()
    messages: Mapped[List["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(Base, PrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "chat_messages"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id"), index=True, nullable=False
    )
    # Null for bot messages; set to the sending user's id for human messages.
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ChatRole] = enum_column(ChatRole, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # `metadata` is reserved on the Declarative Base, so the attribute is named
    # `metadata_json` (DB column matches).
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    user: Mapped[Optional["User"]] = relationship()


from app.models.user import User  # noqa: E402,F401
