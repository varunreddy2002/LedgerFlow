from langgraph.graph import StateGraph, END, START
from app.core.logging import get_logger

from app.application.agents.categorization import (
    CategorizationState,
    load_data, match_party, apply_rules, has_unmatched, llm_categorize, persist
)

logger = get_logger(__name__)

def build_categorization_graph():
    c_graph = StateGraph(CategorizationState)
    c_graph.add_node("load_data", load_data)
    c_graph.add_node("match_party", match_party)
    c_graph.add_node("apply_rules", apply_rules)
    c_graph.add_node("llm_categorize", llm_categorize)
    c_graph.add_node("persist", persist)

    # wire the edges
    c_graph.add_edge(START, "load_data")
    c_graph.add_edge("load_data", "match_party")
    c_graph.add_edge("match_party", "apply_rules")
    c_graph.add_conditional_edges(
        "apply_rules",
        has_unmatched,
        {"llm": "llm_categorize", "persist": "persist"},
    )
    c_graph.add_edge("llm_categorize", "persist")
    c_graph.add_edge("persist", END)

    return c_graph.compile()


# compiled once on import
categorization_graph = build_categorization_graph()


def run_categorization(business_id: int) -> dict:
    """Entry point — categorize all uncategorized transactions for a business."""
    logger.info("Categorization started: business_id=%s", business_id)

    initial_state: CategorizationState = {
        "business_id": business_id,
        "pending": [],
        "categories": [],
        "vendors": [],
        "customers": [],
        "rules": [],
        "unmatched": [],
        "assignments": {},
        "party_assignments": {},
    }

    result = categorization_graph.invoke(initial_state)
    logger.info("Categorization finished: business_id=%s assigned=%d", business_id, len(result["assignments"]))
    return result
    
