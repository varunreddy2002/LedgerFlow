"""Entry points into the chat graph.

Callers:
- run_chat / resume_chat: blocking — return the final answer or a pending interrupt
- stream_chat / stream_resume: yield the agent's reasoning trace as UI events
"""

from langgraph.types import Command

from app.core.logging import get_logger
from app.application.agents.chat.graph import chat_graph
from app.application.agents.chat.streaming import stream_graph_events

logger = get_logger(__name__)


def _initial_state(message: str, business_id: int) -> dict:
    """The full ChatState for a fresh turn (chart_* fields reset)."""
    return {
        "messages": [{"role": "user", "content": message}],
        "business_id": business_id,
        "pending_write": None,
        "chart_description": None,
        "chart_data": None,
        "chart_code": None,
        "chart_confirmed": None,
        "chart_image": None,
        "chart_error": None,
        "chart_retry_count": 0,
    }


def run_chat(message: str, business_id: int, thread_id: str) -> dict:
    """Send a user message. Returns dict with either the final answer or a pending interrupt."""
    logger.info("[chat.run_chat] business_id=%s thread=%s q=%s", business_id, thread_id, message)

    config = {"configurable": {"thread_id": thread_id}}
    chat_graph.invoke(_initial_state(message, business_id), config=config)
    return _extract_result(config)


def resume_chat(thread_id: str, confirmed: bool) -> dict:
    """Resume a paused chart_confirm interrupt with the user's decision."""
    logger.info("[chat.resume_chat] thread=%s confirmed=%s", thread_id, confirmed)

    config = {"configurable": {"thread_id": thread_id}}
    chat_graph.invoke(Command(resume=confirmed), config=config)

    return _extract_result(config)


def _extract_result(config: dict) -> dict:
    """Read graph state after an invoke — either paused at interrupt, or done."""
    state = chat_graph.get_state(config)

    if state.tasks and state.tasks[0].interrupts:
        interrupt_val = state.tasks[0].interrupts[0].value
        logger.info("[chat._extract_result] status=pending_chart payload=%s", interrupt_val)
        return {"status": "pending_chart", "interrupt": interrupt_val}

    answer = state.values["messages"][-1].content
    chart_image = state.values.get("chart_image")
    logger.info("[chat._extract_result] status=done answer_len=%d chart=%s",
                len(answer or ""), bool(chart_image))
    return {"status": "done", "answer": answer, "chart_image": chart_image}


# ── streaming variants ─────────────────────────────────────────────────────
def stream_chat(message: str, business_id: int, thread_id: str):
    """Yield UI event dicts (steps, tool calls/results, tokens, done/interrupt)
    for a new user turn."""
    logger.info("[chat.stream_chat] business_id=%s thread=%s q=%s", business_id, thread_id, message)
    config = {"configurable": {"thread_id": thread_id}}
    yield from stream_graph_events(chat_graph, _initial_state(message, business_id), config)


def stream_resume(thread_id: str, confirmed: bool):
    """Yield UI event dicts for resuming a paused chart_confirm interrupt."""
    logger.info("[chat.stream_resume] thread=%s confirmed=%s", thread_id, confirmed)
    config = {"configurable": {"thread_id": thread_id}}
    yield from stream_graph_events(chat_graph, Command(resume=confirmed), config)
