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


# --- Chat endpoint I/O ----------------------------------------------------
class ChatRequest(BaseModel):
    """Incoming chat message. session_id is null to start a new conversation."""
    message: str
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    """The agent's answer plus the session it belongs to.

    When status == "pending_chart", the graph paused for user confirmation:
    `answer` is None, `interrupt` carries the payload from the paused node,
    and the frontend must call POST /chat/resume with confirmed=true/false.
    """
    session_id: int
    status: str = "done"                     # "done" | "pending_chart"
    answer: Optional[str] = None
    chart_image: Optional[str] = None        # base64 PNG when a chart was generated this turn
    interrupt: Optional[Any] = None          # only set when status == "pending_chart"


class ResumeRequest(BaseModel):
    """Frontend's answer to a pending chart_confirm interrupt."""
    session_id: int
    confirmed: bool


class ChatTurn(ORMModel):
    """One persisted message, for loading conversation history in the UI."""
    id: int
    role: ChatRole
    message: str
    agent_name: Optional[str] = None
    created_at: datetime
