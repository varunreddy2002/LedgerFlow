"""Chat endpoints — talk to the finance agent, list sessions, load history.

Routes
------
POST /api/businesses/{business_id}/chat              — send a message. May return a
                                                       pending_chart interrupt awaiting
                                                       user confirmation.
POST /api/businesses/{business_id}/chat/resume       — approve/decline a paused chart
GET  /api/businesses/{business_id}/chat/sessions     — list conversations
GET  /api/chat/sessions/{session_id}/messages        — load one conversation
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.database import get_db
from app.domain.models import ChatSession, ChatMessage
from app.domain.schemas import ChatRequest, ChatResponse, ChatSessionOut, ChatTurn, ResumeRequest
from app.application.agents.chat.service import handle_chat, handle_resume

router = APIRouter(tags=["chat"])


# To-do need to implement the User RBAC
@router.post("/businesses/{business_id}/chat", response_model=ChatResponse)
def chat(business_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    session_id, answer, interrupt_val = handle_chat(
        db, business_id, payload.message, payload.session_id,
    )
    if interrupt_val is not None:
        # interrupt payload carries a "type": "review_confirm" | "chart_confirm"
        status = interrupt_val.get("type", "interrupt") if isinstance(interrupt_val, dict) else "interrupt"
        return ChatResponse(
            session_id=session_id,
            status=status,
            interrupt=interrupt_val,
        )
    return ChatResponse(session_id=session_id, status="done", answer=answer)


@router.post("/businesses/{business_id}/chat/resume", response_model=ChatResponse)
def resume(business_id: int, payload: ResumeRequest, db: Session = Depends(get_db)):
    session_id, answer, chart_image = handle_resume(
        db, business_id, payload.session_id, payload.confirmed,
    )
    return ChatResponse(
        session_id=session_id,
        status="done",
        answer=answer,
        chart_image=chart_image,
    )


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
