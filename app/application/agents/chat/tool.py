import re
import json
from langchain.tools import tool
from sqlalchemy import text

from app.infrastructure.db.database import engine
from app.core.logging import get_logger
from langchain_core.runnables import RunnableConfig
logger = get_logger(__name__)

# whole-word match so "created_at" isn't caught by "create", etc.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
    re.IGNORECASE,
)


@tool
def query_database(sql: str) -> str:
    """Run a read-only SQL SELECT against the financial database and return the rows as JSON.

    Use this to answer questions about transactions, categories, vendors, customers,
    and spending. Write standard PostgreSQL. Only a single SELECT statement is allowed.
    Always filter by the correct business_id.

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
    except Exception as e:
        logger.warning("query_database error: %s", e)
        return json.dumps([{"error": str(e)}])


@tool
def get_pnl(business_id: int, start_date: str, end_date: str, config: RunnableConfig) -> str:
    """Compute trusted cash-basis P&L for a business over a period.

    Use this for profit/loss, net income, total revenue, or total expenses questions.

    Args:
        business_id: the business to analyze
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
    """
    from app.application.agents.pnl.graph import run_pnl
    result = run_pnl(business_id, start_date, end_date, config=config)
    return json.dumps(result, default=str)


@tool
def request_chart(description: str, data_json: str) -> str:
    """Signal that the user wants a chart. Call query_database FIRST to get the data,
    then pass its JSON result here as data_json. The graph will handle code generation,
    user confirmation, and rendering.

    Args:
        description: what the chart should show (e.g. "bar chart of monthly expenses")
        data_json: the JSON string returned by query_database
    """
    return "chart_requested"