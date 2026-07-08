"""Entry points into the chat graph.

Two callers:
- run_chat: start a new turn (or continue after a completed one)
- resume_chat: resume a paused chart_confirm interrupt
"""

from langgraph.types import Command

from app.core.logging import get_logger
from app.application.agents.chat.graph import chat_graph

logger = get_logger(__name__)


def run_chat(message: str, business_id: int, thread_id: str) -> dict:
    """Send a user message. Returns dict with either the final answer or a pending interrupt."""
    logger.info("[chat.run_chat] business_id=%s thread=%s q=%s", business_id, thread_id, message)

    config = {"configurable": {"thread_id": thread_id}}

    chat_graph.invoke(
        {
            "messages": [
                {"role": "user", "content": f"business_id={business_id}\n\nQuestion: {message}"}
            ],
            "business_id": business_id,
            "chart_description": None,
            "chart_data": None,
            "chart_code": None,
            "chart_confirmed": None,
            "chart_image": None,
            "chart_error": None,
            "chart_retry_count": 0,
        },
        config=config,
    )

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
