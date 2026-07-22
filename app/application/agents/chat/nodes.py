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
DATABASE SCHEMA (PostgreSQL). Every table has a bigint primary key `id`.
This is a double-entry ledger core, not a flat transaction list.

========== CORE FINANCIAL TABLES ==========

businesses(id, name, business_type, currency)

accounts(id, business_id, account_code, account_name, account_type, account_subtype,
         parent_account_id, hierarchy_level, normal_balance, posting_allowed, is_active)
    - the chart of accounts (COA), a fixed 3-level tree via parent_account_id
    - account_type: 'asset' | 'liability' | 'revenue' | 'expense' (no separate 'equity' type —
      owner's equity lives under 'liability' with account_subtype='equity')
    - normal_balance: 'debit' | 'credit' — which side increases this account's balance
      (stored per-account so contra accounts, e.g. Owner Draws, can override the type default)
    - only posting_allowed=true rows (level-3 leaves) can be posted to; levels 1-2 are rollup-only

bank_transactions(id, business_id, document_id, account_id, external_transaction_id,
                   transaction_date, posted_date, description, normalized_description,
                   amount, direction, fingerprint_hash, status)
    - raw rows imported from a bank statement CSV — source evidence, NOT yet an accounting
      interpretation. account_id is the cash/bank leaf this statement belongs to (e.g. Operating Checking)
    - amount: NUMERIC(14,2), always POSITIVE; direction: 'inflow' | 'outflow' carries the sign
    - status: 'new' | 'processing' | 'review_required' | 'processed' | 'excluded' | 'failed'
      ('processed' means a transactions/transaction_entries pair now exists for this row)

transactions(id, business_id, bank_transaction_id, transaction_date, name, description,
             status, confidence_score, reviewed_by, reviewed_at, review_notes, posted_at)
    - the accounting event header (e.g. "AWS payment"). Carries NO amount itself —
      amounts live on transaction_entries. Has business_id directly.
    - status: 'proposed' | 'review_required' | 'approved' | 'rejected' | 'posted' | 'reversed' | 'failed'

transaction_entries(id, transaction_id, account_id, amount, description)
    - one debit or credit line inside a transaction. amount is SIGNED:
      positive = debit, negative = credit. A balanced transaction's entries sum to 0.
    - NO business_id — join transaction_id -> transactions.business_id to scope

accounting_rules(id, business_id, rule_name, rule_type, conditions, actions, priority, status)
    - deterministic classification rules matched against bank_transactions.normalized_description
    - conditions/actions are JSONB; status: 'active' | 'inactive' | 'archived'

invoices(id, business_id, document_id, customer_id, invoice_number, invoice_date, due_date,
         status, bank_transaction_id, accounting_transaction_id)
    - a customer invoice. Cash-basis rule: creating this does NOT create revenue —
      only once bank_transaction_id/accounting_transaction_id are linked to an actual payment
    - status: 'draft' | 'unpaid' | 'paid' | 'void'
invoice_lines(id, invoice_id, line_number, description, quantity, unit_price, tax_amount, revenue_account_id)
    - line total = quantity * unit_price; not stored, derive it. NO business_id — join via invoice_id.

bills(id, business_id, document_id, vendor_id, bill_number, bill_date, due_date,
      status, bank_transaction_id, accounting_transaction_id)
    - a vendor bill. Same cash-basis rule as invoices: no expense until linked to a payment.
bill_lines(id, bill_id, line_number, description, quantity, unit_price, tax_amount, expense_account_id)
    - NO business_id — join via bill_id.

vendors(id, business_id, vendor_name, normalized_name, email, phone, default_account_id, status)
customers(id, business_id, customer_name, normalized_name, email, phone, status)

documents(id, business_id, party_id, source, filename, status, uploaded_at, processed_at)
    - source: 'bank_statement' | 'credit_card' | 'vendor_bill' | 'invoice'
    - status: 'uploaded' | 'processing' | 'processed' | 'failed'

document_extractions(id, document_id, extraction_type, raw_text, extracted_json, model_used, confidence_score)
    - raw OCR/LLM output per document (audit trail). extracted_json is JSON. NO business_id — join via document_id.

audit_events(id, business_id, entity_type, entity_id, event_type, actor_type, actor_id,
             old_values, new_values, reason, correlation_id)
    - append-only, polymorphic by (entity_type, entity_id) — no FK on entity_id.

========== SYSTEM TABLES (ignore unless explicitly asked) ==========

users(id, business_id, name, email, is_active)
chat_sessions(id, thread_id, business_id, user_id, title)
chat_messages(id, session_id, role, message, agent_name, token_usage, metadata_json)

========== KEY RULES ==========
- Most tables have business_id directly (accounts, bank_transactions, transactions, invoices,
  bills, vendors, customers, accounting_rules, documents, audit_events). transaction_entries,
  invoice_lines, and bill_lines do NOT — join up to their parent row to scope by business.
- IMPORTANT — current implementation state: categorization/posting is not wired up yet.
  Expect most bank_transactions to have status='new' with no matching transactions row, and
  transaction_entries/accounting_rules to be empty or sparse. Don't assume posted ledger data
  exists just because bank_transactions do.
- Cash-basis only: no accrual, depreciation, or deferred-revenue concepts anywhere in this schema.
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
