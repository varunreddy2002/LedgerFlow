"""Chat endpoints — talk to the finance agent, list sessions, load history.

Routes
------
POST /api/businesses/{business_id}/chat              — send a message, get an answer
GET  /api/businesses/{business_id}/chat/sessions     — list conversations
GET  /api/chat/sessions/{session_id}/messages        — load one conversation
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.database import get_db
from app.domain.models import ChatSession, ChatMessage
from app.domain.schemas import ChatRequest, ChatResponse, ChatSessionOut, ChatTurn
from app.application.agents.chat.service import handle_chat

router = APIRouter(tags=["chat"])


@router.post("/businesses/{business_id}/chat", response_model=ChatResponse)
def chat(business_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    session_id, answer = handle_chat(db, business_id, payload.message, payload.session_id)
    return ChatResponse(session_id=session_id, answer=answer)


@router.get("/businesses/{business_id}/chat/sessions", response_model=list[ChatSessionOut])
def list_sessions(business_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ChatSession)
        .filter(ChatSession.business_id == business_id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatTurn])
def get_messages(session_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
