"""Tools exposed to the chat agent.

Three tiers, per the agent architecture:

* **Report** — `get_pnl` wraps the trusted ledger primitive (official numbers).
* **Data / read-only** — `query_ledger` runs a guarded SELECT for ad-hoc questions.
* **Review** — `list_review_items` (read) and `resolve_review_item` (write, *gated*).
* **Skill** — `load_skill` fetches a playbook on demand (deferred loading).

`resolve_review_item` and `request_chart` are **signal tools**: they don't act inside
the tool call. The graph intercepts them and routes through a human-in-the-loop
`interrupt` before anything posts or renders — the money-writing path is never taken
by the model alone.
"""

from __future__ import annotations

import json
import re

from langchain.tools import tool
from sqlalchemy import text

from app.core.logging import get_logger
from app.infrastructure.db.database import engine, session_scope
from app.application.accounting.ledger import LedgerService
from app.application.accounting.repository import SqlAlchemyLedgerRepository
from app.application.accounting.review.service import build_review_service
from app.application.skills import skill_registry

logger = get_logger(__name__)

# Whole-word match so "created_at" isn't caught by "create", etc.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
    re.IGNORECASE,
)


@tool
def load_skill(name: str) -> str:
    """Load a skill playbook by name for step-by-step guidance on a task.

    Call this first when a request matches a skill in the index (e.g. 'pnl_report'
    for profit/loss, 'categorize_review' for the review queue). Returns the full
    playbook and the tools it uses.

    Args:
        name: the skill name exactly as shown in the skill index
    """
    try:
        return skill_registry.load(name).render()
    except Exception as exc:
        return f"Error loading skill {name!r}: {exc}"


@tool
def get_pnl(business_id: int, start_date: str, end_date: str) -> str:
    """Compute the trusted cash-basis P&L for a business over a period.

    Use for profit/loss, net income, revenue, or expense-total questions. Returns a
    hierarchical report (revenue/expense subtrees + net income) as JSON. The numbers
    are official — do not recompute them.

    Args:
        business_id: the business to analyze
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
    """
    from datetime import date

    try:
        with session_scope() as db:
            ledger = LedgerService(SqlAlchemyLedgerRepository(db))
            report = ledger.pnl(business_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
            return json.dumps(report.to_dict(), default=str)
    except Exception as exc:
        logger.warning("get_pnl error: %s", exc)
        return json.dumps({"status": "error", "error": str(exc)})


@tool
def list_review_items(business_id: int, item_type: str | None = None) -> str:
    """List the OPEN items in the review/exception queue as JSON.

    Each item shows id, item_type, description, amount, source, and the
    proposed_account_code (the rule/agent's guess). Use before resolving anything.

    Args:
        business_id: the business whose queue to read
        item_type: optional filter, e.g. 'uncategorized' or 'large_amount'
    """
    from app.domain.enums import ReviewItemType

    try:
        parsed_type = ReviewItemType(item_type) if item_type else None
        with session_scope() as db:
            service = build_review_service(db, business_id)
            views = service.list(item_type=parsed_type)
            return json.dumps([v.to_dict() for v in views], default=str)
    except Exception as exc:
        logger.warning("list_review_items error: %s", exc)
        return json.dumps({"status": "error", "error": str(exc)})


@tool
def resolve_review_item(
    business_id: int, item_id: int, decision: str, account_code: str | None = None
) -> str:
    """Resolve one review item — posts a journal entry after OWNER APPROVAL.

    This does NOT post immediately: it pauses for the owner to confirm the exact entry
    first. Amounts come from the bank row; you only choose the account.

    Args:
        business_id: the business
        item_id: the review item id (from list_review_items)
        decision: 'approved' (post to the proposed account), 'modified'
            (post to account_code instead, and learn a rule), or 'rejected' (dismiss)
        account_code: required when decision='modified' — the account to post to
    """
    # Signal tool: the graph intercepts this and runs the approval interrupt.
    return "awaiting_owner_approval"


@tool
def query_ledger(sql: str) -> str:
    """Run a read-only SQL SELECT against the ledger database and return rows as JSON.

    For ad-hoc questions not covered by get_pnl. Only a single SELECT is allowed.
    Always scope by business_id.

    Args:
        sql: one read-only SQL SELECT statement
    """
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return json.dumps([{"error": "Only SELECT queries are allowed."}])
    if ";" in cleaned:
        return json.dumps([{"error": "Only a single statement is allowed."}])
    if _FORBIDDEN.search(cleaned):
        return json.dumps([{"error": "Query contains a forbidden keyword."}])
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(cleaned)).mappings().all()
        return json.dumps([dict(r) for r in rows], default=str)
    except Exception as exc:
        logger.warning("query_ledger error: %s", exc)
        return json.dumps([{"error": str(exc)}])


@tool
def request_chart(description: str, data_json: str) -> str:
    """Signal that the user wants a chart. Fetch the data FIRST (get_pnl or
    query_ledger), then pass its JSON here as data_json. The graph handles code
    generation, user confirmation, and rendering.

    Args:
        description: what the chart should show (e.g. "bar chart of expenses by account")
        data_json: the JSON string returned by a data tool
    """
    return "chart_requested"
