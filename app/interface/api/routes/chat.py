"""Chat endpoints — talk to the finance agent, list sessions, load history.

Routes
------
POST /api/businesses/{business_id}/chat              — send a message (blocking). May
                                                       return a pending_chart interrupt.
POST /api/businesses/{business_id}/chat/stream       — send a message, stream the agent's
                                                       reasoning trace as SSE events.
POST /api/businesses/{business_id}/chat/resume       — approve/decline a paused chart
POST /api/businesses/{business_id}/chat/resume/stream — resume, streamed as SSE
GET  /api/businesses/{business_id}/chat/sessions     — list conversations
GET  /api/chat/sessions/{session_id}/messages        — load one conversation
"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.database import get_db
from app.domain.models import ChatSession, ChatMessage
from app.domain.schemas import ChatRequest, ChatResponse, ChatSessionOut, ChatTurn, ResumeRequest
from app.application.agents.chat.service import (
    handle_chat, handle_resume, handle_stream, handle_resume_stream,
)

router = APIRouter(tags=["chat"])

# SSE responses must not be buffered by proxies; disable nginx buffering too.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# To-do need to implement the User RBAC
@router.post("/businesses/{business_id}/chat", response_model=ChatResponse)
def chat(business_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    session_id, answer, interrupt_val = handle_chat(
        db, business_id, payload.message, payload.session_id,
    )
    if interrupt_val is not None:
        return ChatResponse(
            session_id=session_id,
            status="pending_chart",
            interrupt=interrupt_val,
        )
    return ChatResponse(session_id=session_id, status="done", answer=answer)


@router.post("/businesses/{business_id}/chat/stream")
def chat_stream(business_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    """Stream the agent's reasoning trace as Server-Sent Events."""
    return StreamingResponse(
        handle_stream(db, business_id, payload.message, payload.session_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/businesses/{business_id}/chat/resume/stream")
def resume_stream(business_id: int, payload: ResumeRequest, db: Session = Depends(get_db)):
    """Resume a paused chart_confirm, streamed as Server-Sent Events."""
    return StreamingResponse(
        handle_resume_stream(db, business_id, payload.session_id, payload.confirmed),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


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
