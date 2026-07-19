"""Chat graph nodes.

Each node returns ``Command(goto, update)`` so routing lives with the node that owns
the decision (Command pattern) — no separate router functions.

The loop is a ReAct agent (``agent`` ⇄ ``run_tools``) with two human-in-the-loop
branches that share the ``interrupt`` mechanism:

* **review approval** — ``run_tools`` → ``review_preview`` → ``review_confirm``
  (interrupt) → ``review_apply``. Nothing posts until the owner confirms.
* **chart** — ``run_tools`` → ``chart_code_gen`` → ``chart_confirm`` (interrupt) →
  ``chart_sandbox``.

The system prompt carries only lightweight grounding + a skill index + a tool index —
the full playbooks are fetched on demand via ``load_skill`` (no 100-line schema dump).
"""

from __future__ import annotations

import json

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.core.logging import get_logger
from app.application.agents.chat.state import ChatState
from app.application.agents.chat.tool import (
    load_skill,
    get_pnl,
    list_review_items,
    resolve_review_item,
    query_ledger,
    request_chart,
)
from app.application.agents import sandbox_service
from app.application.skills import skill_registry

logger = get_logger(__name__)

_llm = ChatBedrockConverse(
    model=settings.default_chat_model,
    region_name=settings.aws_region,
    temperature=0,
)


SYSTEM_PROMPT = """You are LedgerFlow's accounting assistant for a small business.

The books are a proper double-entry ledger:
- accounts: chart of accounts (asset/liability/equity/revenue/expense), a 3-level tree;
  postings happen only at level-3 leaves (e.g. 5330 Cloud Hosting, 4110 Consulting Revenue).
- journal_entries + journal_entry_lines: balanced debit/credit entries. Only POSTED
  entries count in reports. Cash-basis: money-in credits a revenue account, money-out
  debits an expense account, and the bank (asset) side is the other leg.
- bank_transactions: raw bank rows fed through the escalation ladder.
- review_items: the exception queue for rows that couldn't be auto-posted.

Rules of engagement:
- For official numbers (P&L, totals) call get_pnl — never do the arithmetic yourself.
- You choose accounts; you never choose amounts. Posting is gated by owner approval.
- Use query_ledger for ad-hoc read-only questions. Always scope by the business_id given.
- Match the task to a skill and load it first. Be concise."""


def _system_prompt() -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Available skills (load with load_skill):\n{skill_registry.index()}\n\n"
        "Tools: load_skill, get_pnl, list_review_items, resolve_review_item, "
        "query_ledger, request_chart."
    )


_READ_TOOLS = {
    "load_skill": load_skill,
    "get_pnl": get_pnl,
    "list_review_items": list_review_items,
    "query_ledger": query_ledger,
}
_ALL_TOOLS = [
    load_skill, get_pnl, list_review_items, resolve_review_item, query_ledger, request_chart,
]
_agent_model = _llm.bind_tools(_ALL_TOOLS)


# ── agent ────────────────────────────────────────────────────────────────
def agent(state: ChatState, config: RunnableConfig) -> Command:
    logger.info("[chat.agent] START msgs=%d business_id=%s",
                len(state["messages"]), state["business_id"])
    response = _agent_model.invoke(
        [SystemMessage(content=_system_prompt())] + state["messages"], config=config,
    )
    tool_calls = getattr(response, "tool_calls", None) or []
    logger.info("[chat.agent] END tool_calls=%s", [tc["name"] for tc in tool_calls] or ["none"])
    if tool_calls:
        return Command(goto="run_tools", update={"messages": [response]})
    return Command(goto=END, update={"messages": [response]})


# ── run_tools ──────────────────────────────────────────────────────────────
def run_tools(state: ChatState, config: RunnableConfig) -> Command:
    """Execute read tools inline; route signal tools (resolve / chart) to their gates.

    Every tool_call in the message gets a ToolMessage reply (required by the API); a
    single signal tool then diverts the graph to its human-in-the-loop branch.
    """
    tool_calls = state["messages"][-1].tool_calls
    tool_messages = []
    route: Command | None = None
    update: dict = {}

    for tc in tool_calls:
        name, args, tc_id = tc["name"], tc["args"], tc["id"]
        logger.info("[chat.run_tools] tool=%s args_keys=%s", name, list(args.keys()))

        if name == "resolve_review_item" and route is None:
            tool_messages.append(ToolMessage(content="awaiting_owner_approval", tool_call_id=tc_id, name=name))
            update["pending_resolution"] = {
                "business_id": args.get("business_id", state["business_id"]),
                "item_id": args["item_id"],
                "decision": args["decision"],
                "account_code": args.get("account_code"),
            }
            route = Command(goto="review_preview")
        elif name == "request_chart" and route is None:
            tool_messages.append(ToolMessage(content="chart_requested", tool_call_id=tc_id, name=name))
            update.update({
                "chart_description": args["description"],
                "chart_data": args["data_json"],
                "chart_retry_count": 0,
                "chart_error": None,
            })
            route = Command(goto="chart_code_gen")
        else:
            tool_fn = _READ_TOOLS.get(name)
            if tool_fn is None:
                tool_messages.append(ToolMessage(
                    content=json.dumps({"error": f"unknown tool {name}"}),
                    tool_call_id=tc_id, name=name))
                continue
            result = tool_fn.invoke(args, config=config)
            tool_messages.append(ToolMessage(content=result, tool_call_id=tc_id, name=name))

    update["messages"] = tool_messages
    if route is not None:
        return Command(goto=route.goto, update=update)
    return Command(goto="agent", update=update)


# ── review approval branch ─────────────────────────────────────────────────
def review_preview(state: ChatState) -> Command:
    """Compute a read-only preview of the entry the resolution would post."""
    from app.infrastructure.db.database import session_scope
    from app.domain.enums import ApprovalDecision
    from app.application.accounting.review.dtos import ReviewResolution
    from app.application.accounting.review.service import build_review_service

    pending = state["pending_resolution"]
    logger.info("[chat.review_preview] item=%s decision=%s",
                pending["item_id"], pending["decision"])
    try:
        with session_scope() as db:
            service = build_review_service(db, pending["business_id"])
            preview = service.preview(
                pending["item_id"],
                ReviewResolution(
                    decision=ApprovalDecision(pending["decision"]),
                    account_code=pending.get("account_code"),
                    actor="owner",
                ),
            )
    except Exception as exc:
        logger.warning("[chat.review_preview] error: %s", exc)
        return Command(goto="agent", update={
            "pending_resolution": None,
            "messages": [HumanMessage(content=f"[note] Could not prepare that resolution: {exc}")],
        })

    if preview.get("error"):
        return Command(goto="agent", update={
            "pending_resolution": None,
            "messages": [HumanMessage(
                content=f"[note] That resolution is invalid: {preview['error']}. "
                        f"Ask the owner for a different account.")],
        })

    return Command(goto="review_confirm", update={"review_preview": preview})


def review_confirm(state: ChatState) -> Command:
    """INTERRUPT — pause for the owner to confirm the exact entry before posting."""
    preview = state["review_preview"]
    logger.info("[chat.review_confirm] INTERRUPT item=%s", preview.get("review_item_id"))
    confirmed = interrupt({"type": "review_confirm", "preview": preview})
    logger.info("[chat.review_confirm] resumed confirmed=%s", confirmed)

    if confirmed:
        return Command(goto="review_apply")
    return Command(goto="agent", update={
        "pending_resolution": None,
        "messages": [HumanMessage(content="[note] The owner declined to post this entry. "
                                          "Acknowledge and offer to revisit it later.")],
    })


def review_apply(state: ChatState) -> Command:
    """Post the approved resolution via the review service (the only write path)."""
    from app.infrastructure.db.database import session_scope
    from app.domain.enums import ApprovalDecision
    from app.application.accounting.review.dtos import ReviewResolution
    from app.application.accounting.review.service import build_review_service

    pending = state["pending_resolution"]
    try:
        with session_scope() as db:
            service = build_review_service(db, pending["business_id"])
            result = service.resolve(
                pending["item_id"],
                ReviewResolution(
                    decision=ApprovalDecision(pending["decision"]),
                    account_code=pending.get("account_code"),
                    actor="owner",
                ),
            )
        note = f"[note] Resolution applied: {json.dumps(result.to_dict(), default=str)}. " \
               f"Summarize what was booked for the owner."
        logger.info("[chat.review_apply] item=%s status=%s je=%s",
                    pending["item_id"], result.status, result.journal_entry_id)
    except Exception as exc:
        logger.warning("[chat.review_apply] error: %s", exc)
        note = f"[note] Posting failed: {exc}. Apologize and suggest next steps."

    return Command(goto="agent", update={
        "pending_resolution": None,
        "review_result": None,
        "messages": [HumanMessage(content=note)],
    })


# ── chart branch (existing capability, retained) ────────────────────────────
def chart_code_gen(state: ChatState, config: RunnableConfig) -> Command:
    retry = state.get("chart_retry_count", 0)
    error = state.get("chart_error")
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
    logger.info("[chat.chart_code_gen] code_len=%d retry=%d", len(code), retry)
    return Command(goto="chart_confirm", update={"chart_code": code})


def chart_confirm(state: ChatState) -> Command:
    logger.info("[chat.chart_confirm] INTERRUPT — waiting for user")
    confirmed = interrupt({"type": "chart_confirm", "description": state["chart_description"]})
    if confirmed:
        return Command(goto="chart_sandbox", update={"chart_confirmed": True})
    return Command(goto="agent", update={
        "chart_confirmed": False,
        "messages": [HumanMessage(content="[note] The user declined chart generation. "
                                          "Provide a brief text answer instead.")],
    })


def chart_sandbox(state: ChatState) -> Command:
    retry = state.get("chart_retry_count", 0)
    try:
        png_b64 = sandbox_service.run(state["chart_code"])
        logger.info("[chat.chart_sandbox] SUCCESS png_bytes=%d", len(png_b64))
        return Command(goto="agent", update={
            "chart_image": png_b64, "chart_error": None,
            "messages": [HumanMessage(content="[note] Chart rendered successfully. Write a brief "
                                              "1-2 sentence summary of the key insight.")],
        })
    except Exception as e:
        err = str(e)[:300]
        logger.warning("[chat.chart_sandbox] FAILED retry=%d error=%s", retry, err)
        if retry < 1:
            return Command(goto="chart_code_gen",
                           update={"chart_error": err, "chart_retry_count": retry + 1})
        return Command(goto="agent", update={
            "chart_error": err,
            "messages": [HumanMessage(content="[note] Chart generation failed after retries. "
                                              "Provide a brief text answer instead.")],
        })
