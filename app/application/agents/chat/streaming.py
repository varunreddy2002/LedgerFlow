"""Turn a LangGraph run into a stream of UI events (the agent's reasoning trace).

The frontend consumes these over SSE (see routes/chat.py). Event types:

    step        — a graph node ran            {"type":"step","node":...}
    tool_call   — the agent decided to call    {"type":"tool_call","name":...,"args":{...}}
    tool_result — a tool returned              {"type":"tool_result","name":...,"content":"..."}
    token       — an answer token chunk        {"type":"token","text":"..."}
    interrupt   — graph paused for the user     {"type":"interrupt","payload":{...}}
    done        — graph finished                {"type":"done","answer":"...","chart_image":...}
    error       — something failed              {"type":"error","message":"..."}

We drive the graph with stream_mode=["updates","messages"]:
  - "updates" gives one {node: state_update} per node -> step / tool_call / tool_result
  - "messages" gives (chunk, metadata) LLM token chunks -> token (agent node only,
    so chart-code-generation tokens don't leak into the answer stream).
"""

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.core.logging import get_logger

logger = get_logger(__name__)


def sse(event: dict) -> str:
    """Serialize one event as an SSE `data:` frame."""
    return f"data: {json.dumps(event, default=str)}\n\n"


def _text_of(msg) -> str:
    """Extract plain text from a message/chunk whose content may be a string or a
    list of Bedrock content blocks."""
    content = getattr(msg, "content", "") or ""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text" or "text" in block:
                parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def _updates_to_events(node: str, update: dict):
    """Yield events for one node's state update."""
    yield {"type": "step", "node": node}

    messages = (update or {}).get("messages") if isinstance(update, dict) else None
    for m in messages or []:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", None) or []:
                yield {"type": "tool_call", "name": tc["name"], "args": tc["args"]}
        elif isinstance(m, ToolMessage):
            content = m.content if isinstance(m.content, str) else str(m.content)
            yield {"type": "tool_result", "name": m.name, "content": content[:2000]}


def stream_graph_events(graph, graph_input, config):
    """Run the graph and yield UI event dicts, ending with a terminal
    `done` or `interrupt` event read from the final graph state."""
    try:
        for mode, chunk in graph.stream(
            graph_input, config=config, stream_mode=["updates", "messages"]
        ):
            if mode == "messages":
                msg_chunk, meta = chunk
                if meta.get("langgraph_node") == "agent":
                    text = _text_of(msg_chunk)
                    if text:
                        yield {"type": "token", "text": text}
            elif mode == "updates":
                for node, update in chunk.items():
                    yield from _updates_to_events(node, update)
    except Exception as e:  # surface failures to the client instead of a dead stream
        logger.exception("[chat.stream] graph error")
        yield {"type": "error", "message": str(e)[:300]}
        return

    yield _terminal_event(graph, config)


def _terminal_event(graph, config) -> dict:
    """After the stream drains, inspect state: paused at an interrupt, or done."""
    state = graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        return {"type": "interrupt", "payload": state.tasks[0].interrupts[0].value}

    answer = _text_of(state.values["messages"][-1])
    return {
        "type": "done",
        "answer": answer,
        "chart_image": state.values.get("chart_image"),
    }
