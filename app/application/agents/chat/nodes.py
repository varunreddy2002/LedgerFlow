"""Chat graph nodes. Each node returns Command(goto, update) so the routing
lives with the node that owns the decision — no separate router functions."""

import json
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.core.logging import get_logger
from app.application.agents.chat.state import ChatState
from app.application.agents.chat.tool import query_database, get_pnl, request_chart
from app.application.agents import sandbox_service

logger = get_logger(__name__)

_haiku = ChatBedrockConverse(
    model=settings.default_chat_model,
    region_name=settings.aws_region,
    temperature=0,
)

SCHEMA = """
DATABASE SCHEMA (PostgreSQL). Every table has an integer primary key `id`.

========== CORE FINANCIAL TABLES ==========

businesses(id, name, business_type, currency)

accounts(id, business_id, account_name, account_type, institution_name, last_four, currency)
    - account_type: 'checking' | 'savings' | 'credit_card' | 'cash' | 'other'

documents(id, business_id, party_id, source, filename, status, uploaded_at, processed_at)
    - source: 'bank_statement' | 'credit_card' | 'vendor_bill' | 'invoice'
    - status: 'uploaded' | 'processing' | 'processed' | 'failed'

transactions(id, document_id, party_id, vendor_id, customer_id, description,
             date, due_date, amount, trans_type, category_id, review_status, fingerprint_hash)
    - amount: NUMERIC(14,2), always POSITIVE
    - trans_type: 'debit'   -> money OUT of bank (bank statement / credit card)
                  'credit'  -> money IN to bank (bank statement / credit card)
                  'payable' -> we owe (from vendor bill PDF, no cash movement yet)
                  'receivable' -> owed to us (from invoice PDF, no cash movement yet)
    - review_status: 'uncategorized' | 'needs_review' | 'auto_approved' | 'user_approved' | 'user_corrected' | 'ignored'
    - transactions have NO business_id -> JOIN documents to scope by business
    - FKs: document_id->documents.id, category_id->categories.id,
           vendor_id->vendors.id, customer_id->customers.id

transaction_line_items(id, transaction_id, description, quantity, unit_price, tax_amount, category_id, review_status)
    - one row per line item from PDF invoices / bills
    - amount per line = quantity * unit_price
    - FKs: transaction_id->transactions.id, category_id->categories.id

categories(id, business_id, name, parent_category_id, category_type)
    - category_type: 'revenue' | 'expense' | 'transfer' | 'owner_draw'
    - self-referential tree via parent_category_id

vendors(id, business_id, name)
customers(id, business_id, name)

document_extractions(id, document_id, extraction_type, raw_text, extracted_json, model_used, confidence_score)
    - raw OCR/LLM output per PDF document (audit trail)
    - extracted_json is JSONB

categorization_rules(id, business_id, pattern, match_field, category_id, confidence, priority, is_system)
    - regex rules that auto-assign categories
    - lower priority tried first

========== SYSTEM TABLES (ignore unless explicitly asked) ==========

users(id, business_id, name, email, is_active)
chat_sessions(id, thread_id, business_id, user_id, title)
chat_messages(id, session_id, role, message, agent_name, token_usage, metadata_json)
audit_logs(id, business_id, user_id, action, entity_type, entity_id, old_value, new_value)

========== KEY RULES ==========
- Scope transactions to a business by joining documents:
      JOIN documents d ON d.id = transactions.document_id WHERE d.business_id = <business_id>
- categories, vendors, customers, accounts have business_id directly.
- Bank / cash rows:  d.source IN ('bank_statement','credit_card')  -> trans_type IN ('debit','credit')
- Invoices / bills:  d.source IN ('vendor_bill','invoice')          -> trans_type IN ('payable','receivable')
- Cash-basis P&L counts only bank / cash rows. Invoices / bills are expectations, not cash.
- For line-item detail on PDFs, JOIN transaction_line_items ON transaction_id.
"""

SYSTEM_PROMPT = f"""You are a financial analyst assistant for a small business.

Tools:
- query_database: for ANY data question. Returns JSON rows.
- get_pnl: for profit/loss, net income, revenue, or expense totals over a period.
- request_chart: use ONLY when a chart makes the answer clearer than text.
    * Trend, comparison, ranking, or top-N questions.
    * You MUST call query_database (or get_pnl) FIRST, then pass its exact JSON
      output as data_json, plus a description of what to plot.
    * Do NOT use for simple factual or yes/no questions.

{SCHEMA}

Always filter by the business_id you are given. Be concise.
"""

_TOOL_REGISTRY = {"query_database": query_database, "get_pnl": get_pnl}
_agent_model = _haiku.bind_tools([query_database, get_pnl, request_chart])


# ── agent ────────────────────────────────────────────────────────────────
def agent(state: ChatState, config: RunnableConfig) -> Command:
    logger.info("[chat.agent] START msgs=%d business_id=%s",
                len(state["messages"]), state["business_id"])

    response = _agent_model.invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"],
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
    tc = state["messages"][-1].tool_calls[0]
    name, args, tc_id = tc["name"], tc["args"], tc["id"]
    logger.info("[chat.run_tools] tool=%s args_keys=%s", name, list(args.keys()))

    if name == "request_chart":
        logger.info("[chat.run_tools] chart requested desc=%r", args["description"])
        return Command(
            goto="chart_code_gen",
            update={
                "chart_description": args["description"],
                "chart_data": args["data_json"],
                "chart_retry_count": 0,
                "chart_error": None,
                "messages": [ToolMessage(
                    content="chart_requested", tool_call_id=tc_id, name=name,
                )],
            },
        )

    tool_fn = _TOOL_REGISTRY[name]
    result = tool_fn.invoke(args, config=config)
    logger.info("[chat.run_tools] tool=%s result_len=%d", name, len(result))
    return Command(
        goto="agent",
        update={"messages": [ToolMessage(content=result, tool_call_id=tc_id, name=name)]},
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

    response = _haiku.invoke(prompt, config=config)
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
