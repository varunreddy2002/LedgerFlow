"""calculate_report — thin, deterministic financial reports.

Each report is a fixed, reviewed SQL template. The database does the arithmetic
(SUM/GROUP BY) and Python does the roll-up totals — the LLM never adds figures
itself. Skills decide *which* report to run and how to present it; this tool only
computes trusted numbers. `business_id` is injected from state, never an LLM arg.

Sign convention: transaction_entries.amount is signed (+debit / -credit). Each
account's natural-direction amount is `+sum` when normal_balance='debit' and
`-sum` when 'credit', so credit-normal revenue and the debit-normal Owner Draws
contra account both come out with the correct sign.

Only status IN ('approved','posted') is counted — proposed / review_required
rows are unreviewed guesses and are excluded from trusted reports.
"""

import json
from decimal import Decimal
from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import text

from app.infrastructure.db.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

REPORT_TYPES = ("pnl", "balance_sheet", "cash_summary")

# Natural-direction amount per account, aggregated from signed entries.
_NATURAL = "CASE WHEN a.normal_balance = 'debit' THEN SUM(te.amount) ELSE -SUM(te.amount) END"

# P&L: revenue + expense movement over [start, end].
_PNL_SQL = f"""
SELECT a.account_type, a.account_code, a.account_name, {_NATURAL} AS amount
FROM transaction_entries te
JOIN transactions t ON t.id = te.transaction_id
JOIN accounts a ON a.id = te.account_id
WHERE t.business_id = :business_id
  AND a.account_type IN ('revenue', 'expense')
  AND t.transaction_date BETWEEN :start_date AND :end_date
  AND t.status IN ('approved', 'posted')
GROUP BY a.account_type, a.account_code, a.account_name, a.normal_balance
ORDER BY a.account_type, a.account_code
"""

# Balance sheet: asset + liability balances as of end_date (cumulative).
_BALANCE_SHEET_SQL = f"""
SELECT a.account_type, a.account_code, a.account_name, {_NATURAL} AS balance
FROM transaction_entries te
JOIN transactions t ON t.id = te.transaction_id
JOIN accounts a ON a.id = te.account_id
WHERE t.business_id = :business_id
  AND a.account_type IN ('asset', 'liability')
  AND t.transaction_date <= :end_date
  AND t.status IN ('approved', 'posted')
GROUP BY a.account_type, a.account_code, a.account_name, a.normal_balance
ORDER BY a.account_type, a.account_code
"""

# Cash summary: actual cash movement from the bank feed over [start, end].
_CASH_SQL = """
SELECT direction, COUNT(*) AS txn_count, SUM(amount) AS total
FROM bank_transactions
WHERE business_id = :business_id
  AND transaction_date BETWEEN :start_date AND :end_date
GROUP BY direction
"""


def _run(sql: str, params: dict) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x or 0))


def _pnl(business_id: int, start: str, end: str) -> dict:
    rows = _run(_PNL_SQL, {"business_id": business_id, "start_date": start, "end_date": end})
    revenue = sum((_dec(r["amount"]) for r in rows if r["account_type"] == "revenue"), Decimal(0))
    expense = sum((_dec(r["amount"]) for r in rows if r["account_type"] == "expense"), Decimal(0))
    return {
        "report_type": "pnl",
        "period": {"start": start, "end": end},
        "lines": rows,
        "summary": {
            "total_revenue": revenue,
            "total_expense": expense,
            "net_income": revenue - expense,
        },
    }


def _balance_sheet(business_id: int, start: str, end: str) -> dict:
    rows = _run(_BALANCE_SHEET_SQL, {"business_id": business_id, "end_date": end})
    assets = sum((_dec(r["balance"]) for r in rows if r["account_type"] == "asset"), Decimal(0))
    liabilities = sum((_dec(r["balance"]) for r in rows if r["account_type"] == "liability"), Decimal(0))
    return {
        "report_type": "balance_sheet",
        "as_of": end,
        "lines": rows,
        "summary": {
            "total_assets": assets,
            "total_liabilities_and_equity": liabilities,
            # cash-basis: any gap is accumulated net income not yet in an equity account
            "unassigned_difference": assets - liabilities,
        },
    }


def _cash_summary(business_id: int, start: str, end: str) -> dict:
    rows = _run(_CASH_SQL, {"business_id": business_id, "start_date": start, "end_date": end})
    by_dir = {r["direction"]: _dec(r["total"]) for r in rows}
    inflow = by_dir.get("inflow", Decimal(0))
    outflow = by_dir.get("outflow", Decimal(0))
    return {
        "report_type": "cash_summary",
        "period": {"start": start, "end": end},
        "lines": rows,
        "summary": {
            "cash_in": inflow,
            "cash_out": outflow,
            "net_change": inflow - outflow,
        },
    }


_BUILDERS = {"pnl": _pnl, "balance_sheet": _balance_sheet, "cash_summary": _cash_summary}


@tool
def calculate_report(
    report_type: str,
    start_date: str,
    end_date: str,
    business_id: Annotated[int, InjectedState("business_id")],
) -> str:
    """Compute a trusted, deterministic financial report and return it as JSON.

    Use this for profit/loss, balance sheet, or cash-flow questions instead of
    hand-writing aggregation SQL — the accounting logic (sign convention, which
    accounts roll up, cash-basis) is handled correctly here.

    Args:
        report_type: one of 'pnl', 'balance_sheet', 'cash_summary'
        start_date: YYYY-MM-DD (start of period; ignored by balance_sheet)
        end_date: YYYY-MM-DD (end of period, or the as-of date for balance_sheet)
    """
    if report_type not in _BUILDERS:
        return json.dumps({"error": f"report_type must be one of {list(REPORT_TYPES)}"})
    try:
        result = _BUILDERS[report_type](business_id, start_date, end_date)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.warning("calculate_report error: %s", e)
        return json.dumps({"error": str(e)})
