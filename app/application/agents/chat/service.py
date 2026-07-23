"""Chat orchestration with persistence.

Wraps the chat graph (run_chat / resume_chat) with session/message persistence
so conversations survive across requests. The graph itself persists LangGraph
state (including paused interrupts) via PostgresSaver keyed on session.thread_id.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domain.models import ChatSession, ChatMessage
from app.domain.enums import ChatRole
from app.application.agents.chat.chat import run_chat, resume_chat, stream_chat, stream_resume
from app.application.agents.chat.streaming import sse
from app.core.logging import get_logger

logger = get_logger(__name__)


def handle_chat(
    db: Session,
    business_id: int,
    message: str,
    session_id: Optional[int] = None,
) -> tuple[int, Optional[str], Optional[dict]]:
    """Persist user turn, run the graph. Returns (session_id, answer|None, interrupt|None).

    - answer is None + interrupt is a dict when the graph paused for chart confirmation.
    - answer is a string + interrupt is None when the graph finished.
    """
    session = None
    if session_id is not None:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.business_id == business_id)
            .first()
        )
    if session is None:
        session = ChatSession(business_id=business_id, title=message[:60])
        db.add(session)
        db.flush()
        logger.info("New chat session created: id=%s thread=%s", session.id, session.thread_id)

    db.add(ChatMessage(session_id=session.id, role=ChatRole.USER, message=message))

    result = run_chat(message, business_id, session.thread_id)

    if result["status"] == "pending_chart":
        db.commit()
        return session.id, None, result["interrupt"]

    _persist_answer(db, session.id, result)
    db.commit()
    return session.id, result["answer"], None


def handle_resume(
    db: Session,
    business_id: int,
    session_id: int,
    confirmed: bool,
) -> tuple[int, str, Optional[str]]:
    """Resume a paused chart_confirm. Returns (session_id, answer, chart_image_b64|None)."""
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.business_id == business_id)
        .first()
    )
    if session is None:
        raise ValueError(f"chat session {session_id} not found for business {business_id}")

    result = resume_chat(session.thread_id, confirmed)
    _persist_answer(db, session.id, result)
    db.commit()
    return session.id, result["answer"], result.get("chart_image")


def _get_or_create_session(db: Session, business_id: int, session_id: Optional[int], title: str) -> ChatSession:
    session = None
    if session_id is not None:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.business_id == business_id)
            .first()
        )
    if session is None:
        session = ChatSession(business_id=business_id, title=title[:60])
        db.add(session)
        db.flush()
        logger.info("New chat session created: id=%s thread=%s", session.id, session.thread_id)
    return session


def handle_stream(db: Session, business_id: int, message: str, session_id: Optional[int] = None):
    """Persist the user turn, then yield SSE frames of the agent's reasoning
    trace. The final assistant answer is persisted when the `done` event arrives.
    Yields ready-to-send SSE strings."""
    session = _get_or_create_session(db, business_id, session_id, message)
    db.add(ChatMessage(session_id=session.id, role=ChatRole.USER, message=message))
    db.commit()  # durably record the user turn (and new session) before streaming

    # let the client learn the session id up front (needed to resume/continue)
    yield sse({"type": "session", "session_id": session.id})

    final = None
    for event in stream_chat(message, business_id, session.thread_id):
        if event["type"] == "done":
            final = event
        yield sse(event)

    if final is not None:
        _persist_answer(db, session.id, final)
        db.commit()


def handle_resume_stream(db: Session, business_id: int, session_id: int, confirmed: bool):
    """Resume a paused chart_confirm and stream the continuation as SSE frames."""
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.business_id == business_id)
        .first()
    )
    if session is None:
        raise ValueError(f"chat session {session_id} not found for business {business_id}")

    yield sse({"type": "session", "session_id": session.id})

    final = None
    for event in stream_resume(session.thread_id, confirmed):
        if event["type"] == "done":
            final = event
        yield sse(event)

    if final is not None:
        _persist_answer(db, session.id, final)
        db.commit()


def _persist_answer(db: Session, session_id: int, result: dict) -> None:
    """Save assistant text and optional chart image as separate messages."""
    if result.get("answer"):
        db.add(ChatMessage(
            session_id=session_id,
            role=ChatRole.ASSISTANT,
            message=result["answer"],
            agent_name="chat",
        ))
    if result.get("chart_image"):
        db.add(ChatMessage(
            session_id=session_id,
            role=ChatRole.ASSISTANT,
            message=f"IMAGE:{result['chart_image']}",
            agent_name="chat",
        ))
