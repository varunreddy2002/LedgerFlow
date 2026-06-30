from app.infrastructure.db.database import session_scope
from app.domain.models import Transaction, Document, Category, CategorizationRule
from app.domain.enums import ReviewStatus
from app.core.logging import get_logger
from app.application.agents.categorization.state import CategorizationState
import re
from app.core.config import settings
import json
from app.infrastructure.llm import bedrock_service
from app.domain.schemas import CategoryAssignments


logger = get_logger(__name__)

def load_data(state: CategorizationState) -> dict:
    business_id = state["business_id"]

    with session_scope() as db:
        pending = [
            {"id": t.id, "description": t.description or ""}
            for t in db.query(Transaction)
                       .join(Document, Transaction.document_id == Document.id)
                       .filter(
                           Document.business_id == business_id,
                           Transaction.review_status == ReviewStatus.UNCATEGORIZED,
                       )
                       .all()
        ]
        # categories + rules same as before
        ...
    return {"pending": pending, "categories": categories, "rules": rules}


def apply_rules(state: CategorizationState) -> dict:
    pending = state["pending"]
    rules = state["rules"]
    threshold = settings.categorization_confidence_threshold

    assignments: dict[int, dict] = {}
    unmatched: list[dict] = []

    for txn in pending:
        description = txn["description"]

        matched = None
        for rule in rules:                      # rules already in priority order
            if re.search(rule["pattern"], description, re.IGNORECASE):
                matched = rule
                break                           # first match wins

        if matched is None:
            unmatched.append(txn)
            continue

        confidence = matched["confidence"]
        review_status = (
            ReviewStatus.AUTO_APPROVED if confidence >= threshold
            else ReviewStatus.NEEDS_REVIEW
        )
        assignments[txn["id"]] = {
            "category_id": matched["category_id"],
            "confidence": confidence,
            "source": "rule",
            "review_status": review_status,
        }

    logger.info("apply_rules: %d matched, %d unmatched", len(assignments), len(unmatched))
    return {"assignments": assignments, "unmatched": unmatched}


def has_unmatched(state: CategorizationState) -> str:
    """Route: if rules left anything unmatched, go to the LLM; otherwise skip to persist."""
    return "llm" if state["unmatched"] else "persist"



def llm_categorize(state: CategorizationState) -> dict:
    unmatched = state["unmatched"]
    categories = state["categories"]
    name_to_id = {c["name"]: c["id"] for c in categories}

    # IMPORTANT: start from the rule-based assignments and ADD to them
    assignments = dict(state["assignments"])

    prompt = (
        "You are a bookkeeping assistant. For each transaction, choose the single best "
        "category from the provided list. Use the category name EXACTLY as given. "
        "If none of the categories fit, return null for that transaction."
    )
    message = json.dumps({
        "categories": [c["name"] for c in categories],
        "transactions": unmatched,           # [{"id": ..., "description": ...}]
    })

    result = bedrock_service.invoke_structured(message, prompt, CategoryAssignments)

    for item in result.assignments:
        category_id = name_to_id.get(item.category_name) if item.category_name else None
        assignments[item.transaction_id] = {
            "category_id": category_id,
            "confidence": None,
            "source": "llm",
            "review_status": ReviewStatus.NEEDS_REVIEW,
        }

    logger.info("llm_categorize: handled %d unmatched transactions", len(unmatched))
    return {"assignments": assignments}