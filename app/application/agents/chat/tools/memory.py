"""remember / recall — the base semantic-memory tools.

Durable facts about a business or the user's preferences, namespaced per
business in the PostgresStore. `store` and `business_id` are injected (never LLM
args), so memory is always scoped to the current business.

Boundary rule: this is for context with NO home in the accounting schema
(preferences, phrasing, how the owner refers to things). A learned accounting
fact — e.g. "vendor Acme is Office Supplies" — is NOT a memory; it is a
categorization rule and belongs in manage_configuration, so the engine reuses it.
"""

import json
import uuid
from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState, InjectedStore
from langgraph.store.base import BaseStore

from app.application.agents.chat.store import facts_namespace
from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
def remember(
    fact: str,
    business_id: Annotated[int, InjectedState("business_id")],
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """Save a durable fact about this business or the user's preferences so it is
    available in future conversations.

    Use for context that has no home in the accounting data: preferences (e.g.
    "always show amounts rounded"), naming ("the owner calls contractors 'the
    team'"), or business context. Do NOT use this to record which account a
    vendor or keyword maps to — that is a categorization rule; use
    manage_configuration instead.

    Args:
        fact: the fact to remember, as a short self-contained sentence
    """
    store.put(facts_namespace(business_id), uuid.uuid4().hex, {"text": fact})
    logger.info("[memory] remembered for business %s: %s", business_id, fact)
    return f"Remembered: {fact}"


@tool
def recall(
    query: str,
    business_id: Annotated[int, InjectedState("business_id")],
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """Recall previously saved facts/preferences about this business that are
    relevant to the query. Call this when the user refers to a preference or
    context you might have been told before.

    Args:
        query: what to recall about (e.g. "reporting preferences")
    """
    items = store.search(facts_namespace(business_id), limit=50)
    texts = [it.value.get("text", "") for it in items]
    if not texts:
        return json.dumps([])
    terms = [w for w in query.lower().split() if len(w) > 2]
    matched = [t for t in texts if any(w in t.lower() for w in terms)] or texts
    return json.dumps(matched[:10])
