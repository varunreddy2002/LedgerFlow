"""Chat graph — wires the nodes together and compiles with a Postgres checkpointer.

The checkpointer persists graph state (including paused interrupts) so a
chart_confirm interrupt survives across HTTP requests and server restarts.
"""

from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings
from app.core.logging import get_logger
from app.application.agents.chat.state import ChatState
from app.application.agents.chat.nodes import (
    agent, run_tools,
    review_preview, review_confirm, review_apply,
    chart_code_gen, chart_confirm, chart_sandbox,
)

logger = get_logger(__name__)

# Open a Postgres checkpointer against the same DB as the app.
# .setup() creates the checkpoint tables on first run — safe to call every boot.
_cp_ctx = PostgresSaver.from_conn_string(settings.database_url)
checkpointer = _cp_ctx.__enter__()
checkpointer.setup()


def build_chat_graph():
    g = StateGraph(ChatState)
    g.add_node("agent", agent)
    g.add_node("run_tools", run_tools)
    g.add_node("review_preview", review_preview)
    g.add_node("review_confirm", review_confirm)
    g.add_node("review_apply", review_apply)
    g.add_node("chart_code_gen", chart_code_gen)
    g.add_node("chart_confirm", chart_confirm)
    g.add_node("chart_sandbox", chart_sandbox)
    g.set_entry_point("agent")
    return g.compile(checkpointer=checkpointer)


chat_graph = build_chat_graph()
logger.info("chat_graph compiled with PostgresSaver")
