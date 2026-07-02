"""Chat orchestration with persistence.

Wraps the chat agent (run_chat) with session/message persistence so
conversations survive across requests.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domain.models import ChatSession, ChatMessage
from app.domain.enums import ChatRole
from app.application.agents.chat.chat import run_chat
from app.core.logging import get_logger

logger = get_logger(__name__)


def handle_chat(
    db: Session,
    business_id: int,
    message: str,
    session_id: Optional[int] = None,
) -> tuple[int, str]:
    """Persist the user turn, run the agent, persist the answer. Returns (session_id, answer)."""

    # 1) get the existing session (scoped to this business) or start a new one
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
        db.flush()   # get session.id
        logger.info("New chat session created: id=%s business_id=%s", session.id, business_id)

    # 2) save the user's message
    db.add(ChatMessage(session_id=session.id, role=ChatRole.USER, message=message))

    # 3) run the agent
    answer = run_chat(message, business_id)

    # 4) save the assistant's answer
    db.add(ChatMessage(
        session_id=session.id,
        role=ChatRole.ASSISTANT,
        message=answer,
        agent_name="chat",
    ))

    db.commit()
    return session.id, answer
