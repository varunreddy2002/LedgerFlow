"""Schemas for chat sessions and messages."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.models.enums import ChatRole
from app.schemas.base import ORMModel


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
    role: ChatRole
    message: str
    metadata_json: Optional[Any] = None


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageOut(ORMModel, ChatMessageBase):
    id: int
    created_at: datetime
