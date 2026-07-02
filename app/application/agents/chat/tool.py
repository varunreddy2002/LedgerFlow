import re
from langchain.tools import tool
from sqlalchemy import text

from app.infrastructure.db.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

# whole-word match so "created_at" isn't caught by "create", etc.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
    re.IGNORECASE,
)


@tool
def query_database(sql: str) -> list[dict]:
    """Run a read-only SQL SELECT against the financial database and return the rows.

    Use this to answer questions about transactions, categories, vendors, customers,
    and spending. Write standard PostgreSQL. Only a single SELECT statement is allowed.
    Always filter by the correct business_id.

    Args:
        sql: one read-only SQL SELECT statement
    """
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()

    if not (lowered.startswith("select") or lowered.startswith("with")):
        return [{"error": "Only SELECT queries are allowed."}]
    if ";" in cleaned:
        return [{"error": "Only a single statement is allowed."}]
    if _FORBIDDEN.search(cleaned):
        return [{"error": "Query contains a forbidden keyword."}]

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(cleaned)).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("query_database error: %s", e)
        return [{"error": str(e)}]
    

from app.application.agents.pnl.graph import run_pnl


@tool
def get_pnl(business_id: int, start_date: str, end_date: str) -> dict:
    """Compute the trusted cash-basis Profit & Loss (P&L) for a business over a period.

    Use this for questions about profit, loss, net income, total revenue, or total
    expenses over a date range. Returns revenue, expenses, net income, and a
    per-category breakdown. Prefer this over writing your own SQL for P&L numbers.

    Args:
        business_id: the business to analyze
        start_date: period start, YYYY-MM-DD
        end_date: period end, YYYY-MM-DD
    """
    return run_pnl(business_id, start_date, end_date)