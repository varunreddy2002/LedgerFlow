from langgraph.graph import StateGraph, START, END

from app.core.logging import get_logger
from app.application.agents.pnl import PnLState
from app.application.agents.pnl import (
    gate_categorization,
    gate_router,
    load_bank_txns,
    compute_by_category,
    format_report,
)

logger = get_logger(__name__)


def build_pnl_graph():
    g_pnl = StateGraph(PnLState)

    g_pnl.add_node("gate", gate_categorization)
    g_pnl.add_node("load", load_bank_txns)
    g_pnl.add_node("compute", compute_by_category)
    g_pnl.add_node("format", format_report)

    g_pnl.add_edge(START, "gate")
    g_pnl.add_conditional_edges("gate", gate_router, {"fail": "format", "load": "load"})
    g_pnl.add_edge("load", "compute")
    g_pnl.add_edge("compute", "format")
    g_pnl.add_edge("format", END)

    return g_pnl.compile()


pnl_graph = build_pnl_graph()


def run_pnl(business_id: int, start_date: str, end_date: str) -> dict:
    """Entry point — compute cash-basis P&L for a business over a period."""
    logger.info("P&L started: business_id=%s period=%s..%s", business_id, start_date, end_date)

    initial_state: PnLState = {
        "business_id": business_id,
        "start_date": start_date,
        "end_date": end_date,
        "bank_txns": [],
        "report": None,
        "gate_failed": False,
        "uncategorized_count": 0,
    }

    result = pnl_graph.invoke(initial_state)
    return result["report"]