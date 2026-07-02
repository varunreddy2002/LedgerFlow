from datetime import date

from app.infrastructure.db.database import session_scope
from app.domain.models import Transaction, Document, Category
from app.domain.enums import SourceType, CategoryType
from collections import defaultdict
from app.core.logging import get_logger
from app.application.agents.pnl.state import PnLState

logger = get_logger(__name__)

# cash-basis P&L counts only money that actually moved through an account
BANK_SOURCES = [SourceType.BANK_STATEMENT, SourceType.CREDIT_CARD]


def gate_categorization(state: PnLState) -> dict:
    business_id = state["business_id"]
    start = date.fromisoformat(state["start_date"])
    end = date.fromisoformat(state["end_date"])

    with session_scope() as db:
        uncategorized = (
            db.query(Transaction)
            .join(Document, Transaction.document_id == Document.id)
            .filter(
                Document.business_id == business_id,
                Document.source.in_(BANK_SOURCES),
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.category_id.is_(None),      # no category = can't be bucketed
            )
            .count()
        )

    if uncategorized > 0:
        logger.warning("P&L gate FAILED: %d uncategorized bank rows in period", uncategorized)
    else:
        logger.info("P&L gate passed: all bank rows in period are categorized")

    return {"gate_failed": uncategorized > 0, "uncategorized_count": uncategorized}


def gate_router(state: PnLState) -> str:
    """Conditional edge: abort to failure, or proceed to load."""
    return "fail" if state["gate_failed"] else "load"



def load_bank_txns(state: PnLState) -> dict:
    business_id = state["business_id"]
    start = date.fromisoformat(state["start_date"])
    end = date.fromisoformat(state["end_date"])

    with session_scope() as db:
        rows = (
            db.query(Transaction, Category)
            .join(Document, Transaction.document_id == Document.id)
            .join(Category, Transaction.category_id == Category.id)   # inner join = only categorized
            .filter(
                Document.business_id == business_id,
                Document.source.in_(BANK_SOURCES),
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .all()
        )

        bank_txns = [
            {
                "amount": float(t.amount),
                "trans_type": t.trans_type.value,          # "debit" | "credit"
                "category_name": c.name,
                "category_type": c.category_type.value,    # "revenue" | "expense" | ...
            }
            for t, c in rows
        ]

    logger.info("load_bank_txns: loaded %d categorized bank rows", len(bank_txns))
    return {"bank_txns": bank_txns}


def compute_by_category(state: PnLState) -> dict:
    bank_txns = state["bank_txns"]

    # 1) per-category signed net: CREDIT adds, DEBIT subtracts
    cat_net: dict[str, float] = defaultdict(float)
    cat_type: dict[str, str] = {}
    for t in bank_txns:
        signed = t["amount"] if t["trans_type"] == "credit" else -t["amount"]
        cat_net[t["category_name"]] += signed
        cat_type[t["category_name"]] = t["category_type"]

    # 2) bucket each category by its type
    revenue = 0.0
    expenses = 0.0
    by_category = []
    for name, net in cat_net.items():
        ctype = cat_type[name]
        if ctype == CategoryType.REVENUE.value:
            revenue += net
            amount = net                 # revenue = net inflow (positive)
        elif ctype == CategoryType.EXPENSE.value:
            expenses += -net             # outflow magnitude
            amount = -net                # expense shown as positive
        else:
            continue                     # TRANSFER, OWNER_DRAW excluded from P&L
        by_category.append({"category": name, "type": ctype, "amount": round(amount, 2)})

    report = {
        "revenue": round(revenue, 2),
        "expenses": round(expenses, 2),
        "net_income": round(revenue - expenses, 2),
        "by_category": sorted(by_category, key=lambda x: x["amount"], reverse=True),
    }
    logger.info("compute: revenue=%.2f expenses=%.2f net=%.2f",
                report["revenue"], report["expenses"], report["net_income"])
    return {"report": report}



def format_report(state: PnLState) -> dict:
    period = {"start": state["start_date"], "end": state["end_date"]}

    # --- fail path: the gate blocked us, compute never ran ---
    if state.get("gate_failed"):
        report = {
            "status": "failed",
            "reason": (
                f"{state['uncategorized_count']} bank transaction(s) in this period are "
                f"uncategorized. Categorize them before running P&L."
            ),
            "period": period,
        }
        logger.warning("P&L not generated: %d uncategorized bank rows", state["uncategorized_count"])
        return {"report": report}

    # --- success path: wrap the computed numbers with period + status ---
    report = dict(state["report"])          # produced by compute_by_category
    report["status"] = "ok"
    report["period"] = period
    logger.info("P&L report ready: %s..%s", state["start_date"], state["end_date"])
    return {"report": report}