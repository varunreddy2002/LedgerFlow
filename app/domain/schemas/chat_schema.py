"""Schemas for chat sessions and messages."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.domain.enums import ChatRole
from app.domain.schemas.base import ORMModel


# --- ChatSession ----------------------------------------------------------
class ChatSessionBase(BaseModel):
    business_id: int
    title: Optional[str] = None


class ChatSessionCreate(ChatSessionBase):
    pass


class ChatSessionOut(ORMModel, ChatSessionBase):
    id: int
    created_at: datetime


# --- ChatMessage ----------------------------------------------------------
class ChatMessageBase(BaseModel):
    session_id: int
    user_id: Optional[int] = None  # null for bot messages
    role: ChatRole
    message: str
    metadata_json: Optional[Any] = None


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageOut(ORMModel, ChatMessageBase):
    id: int
    created_at: datetime
