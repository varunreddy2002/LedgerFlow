"""Long-term memory store — the base (semantic) layer.

A LangGraph PostgresStore against the same database as the app, opened once at
import (same pattern as the PostgresSaver checkpointer). It holds durable facts
namespaced per business; the remember/recall tools read and write it.

This is deliberately the *base* layer only: simple namespaced key/value facts,
no embeddings. Episodic memory (past-conversation recall via similarity) and
self-improving procedural memory are later avenues, not built here.
"""

from langgraph.store.postgres import PostgresStore

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# .setup() creates the store tables on first run — safe to call every boot.
_store_ctx = PostgresStore.from_conn_string(settings.database_url)
store = _store_ctx.__enter__()
store.setup()
logger.info("chat memory store ready (PostgresStore)")


def facts_namespace(business_id: int) -> tuple[str, str]:
    """Per-business namespace for durable semantic facts."""
    return (str(business_id), "facts")
