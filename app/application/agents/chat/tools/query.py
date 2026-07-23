"""query_database — raw read-only SQL against the ledger, tenant-scoped.

`business_id` is injected from the graph state (`InjectedState`), never an
LLM-supplied argument, so the model cannot point the query at another tenant.
The model scopes queries with the bound `:business_id` parameter; comparing
`business_id` to a numeric literal is rejected outright.

Residual risk (accepted, documented): a query that simply omits any business
filter still returns cross-tenant rows. Fully closing that needs SQL parsing or
Postgres row-level security — future work. This guard stops the model from
*targeting* a specific foreign tenant, which is the main threat here.
"""

import re
import json
from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import text

from app.infrastructure.db.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

# whole-word match so "created_at" isn't caught by "create", etc.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
    re.IGNORECASE,
)
# business_id must be scoped via the bound :business_id param, never a literal —
# blocks the model from hardcoding another tenant's id.
_LITERAL_BID = re.compile(r"business_id\s*=\s*\d", re.IGNORECASE)


@tool
def query_database(sql: str, business_id: Annotated[int, InjectedState("business_id")]) -> str:
    """Run a read-only SQL SELECT against the financial database and return rows as JSON.

    Use this for ANY question about transactions, accounts, vendors, customers,
    invoices, bills, or spending. Write standard PostgreSQL — a single SELECT
    statement only.

    Scope every query to the current business with the bound parameter
    `:business_id` (e.g. `WHERE business_id = :business_id`). Do NOT write a
    literal business id — it is supplied for you, and a literal will be rejected.

    Args:
        sql: one read-only SQL SELECT statement, scoped with :business_id
    """
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()

    if not (lowered.startswith("select") or lowered.startswith("with")):
        return json.dumps([{"error": "Only SELECT queries are allowed."}])
    if ";" in cleaned:
        return json.dumps([{"error": "Only a single statement is allowed."}])
    if _FORBIDDEN.search(cleaned):
        return json.dumps([{"error": "Query contains a forbidden keyword."}])
    if _LITERAL_BID.search(cleaned):
        return json.dumps([{"error": "Do not compare business_id to a literal; "
                                     "use the :business_id parameter."}])

    # Only bind the param when the query references it — SQLAlchemy text() rejects
    # unreferenced binds otherwise.
    params = {"business_id": business_id} if ":business_id" in cleaned else {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(cleaned), params).mappings().all()
        return json.dumps([dict(r) for r in rows], default=str)
    except Exception as e:
        logger.warning("query_database error: %s", e)
        return json.dumps([{"error": str(e)}])
