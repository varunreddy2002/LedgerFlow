"""Chat graph nodes. Each node returns Command(goto, update) so the routing
lives with the node that owns the decision — no separate router functions.

Tool execution uses LangGraph's prebuilt ToolNode: it runs ALL tool calls in a
turn (parallel-safe), injects InjectedState/InjectedStore args, and formats one
ToolMessage per call. run_tools wraps it only to special-case request_chart,
which routes into the chart branch instead of being answered inline.
"""

import json
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.core.logging import get_logger
from app.application.agents.chat.state import ChatState
from app.application.agents.chat.prompts import system_prompt
from app.application.agents.chat.tools import ALL_TOOLS
from app.application.agents.chat.tools.writes import WRITE_TOOLS
from app.application.agents.chat.skills import registry
from app.application.agents import sandbox_service

logger = get_logger(__name__)

_llm = ChatBedrockConverse(
    model=settings.default_chat_model,
    region_name=settings.aws_region,
    temperature=0,
)

# Skill catalog is baked into the system prompt at startup (registry loads once).
_SYSTEM_PROMPT = system_prompt(registry.catalog())
_agent_model = _llm.bind_tools(ALL_TOOLS)
_tool_node = ToolNode(ALL_TOOLS)


# ── agent ────────────────────────────────────────────────────────────────
def agent(state: ChatState, config: RunnableConfig) -> Command:
    logger.info("[chat.agent] START msgs=%d business_id=%s",
                len(state["messages"]), state["business_id"])

    response = _agent_model.invoke(
        [SystemMessage(content=_SYSTEM_PROMPT)] + state["messages"],
        config=config,
    )
    tool_calls = getattr(response, "tool_calls", None) or []
    tool_names = [tc["name"] for tc in tool_calls] or ["none"]
    logger.info("[chat.agent] END tool_calls=%s", tool_names)

    if tool_calls:
        return Command(goto="run_tools", update={"messages": [response]})
    return Command(goto=END, update={"messages": [response]})


# ── run_tools ────────────────────────────────────────────────────────────
def run_tools(state: ChatState, config: RunnableConfig) -> Command:
    """Execute every tool call in the last agent message via ToolNode, then
    route: if the turn asked for a chart, hand off to chart_code_gen; otherwise
    return the tool results to the agent."""
    ai_msg = state["messages"][-1]
    tool_calls = ai_msg.tool_calls
    logger.info("[chat.run_tools] calls=%s", [tc["name"] for tc in tool_calls])

    # ToolNode runs ALL calls (parallel-safe) and injects state/store args.
    # request_chart is a real tool that returns "chart_requested", so it gets a
    # ToolMessage here too — that keeps every tool_use paired with a tool_result.
    result = _tool_node.invoke(state, config)
    new_messages = result["messages"]

    # WRITE tools (checked first): don't commit here — route to human confirmation.
    write_call = next((tc for tc in tool_calls if tc["name"] in WRITE_TOOLS), None)
    if write_call is not None:
        summary = WRITE_TOOLS[write_call["name"]]["summarize"](state["business_id"], write_call["args"])
        logger.info("[chat.run_tools] write pending: %s", summary)
        return Command(
            goto="write_confirm",
            update={
                "pending_write": {
                    "tool": write_call["name"],
                    "args": write_call["args"],
                    "summary": summary,
                },
                "messages": new_messages,
            },
        )

    chart_call = next((tc for tc in tool_calls if tc["name"] == "request_chart"), None)
    if chart_call is not None:
        logger.info("[chat.run_tools] chart requested desc=%r", chart_call["args"]["description"])
        return Command(
            goto="chart_code_gen",
            update={
                "chart_description": chart_call["args"]["description"],
                "chart_data": chart_call["args"]["data_json"],
                "chart_retry_count": 0,
                "chart_error": None,
                "messages": new_messages,
            },
        )

    logger.info("[chat.run_tools] executed=%d results", len(new_messages))
    return Command(goto="agent", update={"messages": new_messages})


# ── write_confirm (INTERRUPT) ────────────────────────────────────────────
def write_confirm(state: ChatState) -> Command:
    """Pause and ask the user to approve a pending write before it commits."""
    pw = state["pending_write"]
    logger.info("[chat.write_confirm] INTERRUPT tool=%s", pw["tool"])
    confirmed = interrupt({
        "type": "write_confirm",
        "tool": pw["tool"],
        "summary": pw["summary"],
    })
    logger.info("[chat.write_confirm] resumed confirmed=%s", confirmed)

    if confirmed:
        return Command(goto="write_execute", update={})

    return Command(
        goto="agent",
        update={
            "pending_write": None,
            "messages": [HumanMessage(
                content="[note] The user DECLINED the write. Do not perform it; acknowledge briefly.",
            )],
        },
    )


# ── write_execute ────────────────────────────────────────────────────────
def write_execute(state: ChatState) -> Command:
    """Perform the confirmed write, then report the outcome back to the agent."""
    pw = state["pending_write"]
    try:
        result = WRITE_TOOLS[pw["tool"]]["execute"](state["business_id"], pw["args"])
    except Exception as e:
        result = f"Write failed: {str(e)[:200]}"
        logger.exception("[chat.write_execute] failed tool=%s", pw["tool"])
    logger.info("[chat.write_execute] tool=%s result=%s", pw["tool"], result)
    return Command(
        goto="agent",
        update={
            "pending_write": None,
            "messages": [HumanMessage(
                content=f"[note] Write completed. Result: {result}. Tell the user plainly.",
            )],
        },
    )


# ── chart_code_gen ───────────────────────────────────────────────────────
def chart_code_gen(state: ChatState, config: RunnableConfig) -> Command:
    retry = state.get("chart_retry_count", 0)
    error = state.get("chart_error")

    row_count = 0
    try:
        parsed = json.loads(state["chart_data"])
        row_count = len(parsed) if isinstance(parsed, list) else 0
    except Exception:
        pass

    logger.info("[chat.chart_code_gen] START desc=%r rows=%d retry=%d",
                state["chart_description"], row_count, retry)

    error_hint = f"\n\nThe previous attempt failed with:\n{error}\nFix it." if error else ""

    prompt = f"""Write Python matplotlib code to visualize this data.

Description: {state['chart_description']}
Data (JSON): {state['chart_data']}

Rules:
- matplotlib.pyplot is imported as plt, pandas as pd
- Do NOT call plt.show() or plt.savefig() — handled externally
- Do NOT print anything
- Label axes and title clearly
- Keep it concise{error_hint}

Return ONLY the Python code. No markdown fences. No explanation."""

    response = _llm.invoke(prompt, config=config)
    code = response.content.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else code
        code = code.rsplit("```", 1)[0].strip()

    logger.info("[chat.chart_code_gen] END code_len=%d", len(code))
    return Command(goto="chart_confirm", update={"chart_code": code})


# ── chart_confirm (INTERRUPT) ────────────────────────────────────────────
def chart_confirm(state: ChatState) -> Command:
    logger.info("[chat.chart_confirm] INTERRUPT — waiting for user")
    confirmed = interrupt({
        "type": "chart_confirm",
        "description": state["chart_description"],
    })
    logger.info("[chat.chart_confirm] resumed confirmed=%s", confirmed)

    if confirmed:
        return Command(goto="chart_sandbox", update={"chart_confirmed": True})

    return Command(
        goto="agent",
        update={
            "chart_confirmed": False,
            "messages": [HumanMessage(
                content="[note] The user declined chart generation. Provide a brief text answer instead based on the data.",
            )],
        },
    )


# ── chart_sandbox ────────────────────────────────────────────────────────
def chart_sandbox(state: ChatState) -> Command:
    retry = state.get("chart_retry_count", 0)
    logger.info("[chat.chart_sandbox] START retry=%d code_len=%d",
                retry, len(state.get("chart_code") or ""))

    try:
        png_b64 = sandbox_service.run(state["chart_code"])
        logger.info("[chat.chart_sandbox] SUCCESS png_bytes=%d", len(png_b64))
        return Command(
            goto="agent",
            update={
                "chart_image": png_b64,
                "chart_error": None,
                "messages": [HumanMessage(
                    content="[note] Chart rendered successfully. Write a brief 1-2 sentence summary of the key insight from the data.",
                )],
            },
        )
    except Exception as e:
        err = str(e)[:300]
        logger.warning("[chat.chart_sandbox] FAILED retry=%d error=%s", retry, err)

        if retry < 1:
            return Command(
                goto="chart_code_gen",
                update={"chart_error": err, "chart_retry_count": retry + 1},
            )

        return Command(
            goto="agent",
            update={
                "chart_error": err,
                "messages": [HumanMessage(
                    content="[note] Chart generation failed after retries. Provide a brief text answer instead based on the data.",
                )],
            },
        )
