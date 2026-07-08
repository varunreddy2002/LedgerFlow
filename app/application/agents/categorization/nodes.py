from app.infrastructure.db.database import session_scope
from app.domain.models import Transaction, Document, Category, CategorizationRule, Vendor, Customer
from app.domain.enums import ReviewStatus, TransactionType
from app.core.logging import get_logger
from app.application.agents.categorization.state import CategorizationState
import re
from app.core.config import settings
import json
from app.infrastructure.llm import BedrockService
from app.domain.schemas import CategoryAssignments


logger = get_logger(__name__)
bedrock_service = BedrockService(settings.default_chat_model)


def load_data(state: CategorizationState) -> dict:
    business_id = state["business_id"]

    with session_scope() as db:
        pending = [
            {
                "id": t.id,
                "description": t.description or "",
                "trans_type": t.trans_type.value,
                "vendor_id": t.vendor_id,
                "customer_id": t.customer_id,
            }
            for t in db.query(Transaction)
                       .join(Document, Transaction.document_id == Document.id)
                       .filter(
                           Document.business_id == business_id,
                           Transaction.review_status == ReviewStatus.UNCATEGORIZED,
                       )
                       .all()
        ]
        categories = [
            {"id": c.id, "name": c.name, "type": c.category_type.value}
            for c in db.query(Category).filter(Category.business_id == business_id).all()
        ]
        vendors = [
            {"id": v.id, "name": v.name}
            for v in db.query(Vendor).filter(Vendor.business_id == business_id).all()
        ]
        customers = [
            {"id": c.id, "name": c.name}
            for c in db.query(Customer).filter(Customer.business_id == business_id).all()
        ]

        rules = [
            {"pattern": r.pattern, "category_id": r.category_id, "confidence": r.confidence or 0.0}
            for r in db.query(CategorizationRule)
                       .filter(CategorizationRule.business_id == business_id)
                       .order_by(CategorizationRule.priority)
                       .all()
        ]

    logger.info(
        "load_data: %d pending, %d categories, %d vendors, %d customers, %d rules",
        len(pending), len(categories), len(vendors), len(customers), len(rules),
    )
    return {
        "pending": pending,
        "categories": categories,
        "vendors": vendors,
        "customers": customers,
        "rules": rules,
    }


def match_party(state: CategorizationState) -> dict:
    """Substring-match transaction descriptions against known vendors/customers.

    Money-out rows (debit/payable) → try vendors.
    Money-in rows  (credit/receivable) → try customers.
    Skips transactions that already have a party set (e.g. from PDF extraction).
    """
    pending = state["pending"]
    vendors = state["vendors"]
    customers = state["customers"]

    OUTFLOW = {TransactionType.DEBIT.value, TransactionType.PAYABLE.value}
    INFLOW = {TransactionType.CREDIT.value, TransactionType.RECEIVABLE.value}

    party_assignments: dict[int, dict] = {}

    for txn in pending:
        if txn.get("vendor_id") or txn.get("customer_id"):
            continue  # already has a party (from PDF ingestion)

        desc = (txn["description"] or "").lower()
        if not desc:
            continue

        if txn["trans_type"] in OUTFLOW:
            for v in vendors:
                if v["name"].lower() in desc:
                    party_assignments[txn["id"]] = {"vendor_id": v["id"]}
                    break
        elif txn["trans_type"] in INFLOW:
            for c in customers:
                if c["name"].lower() in desc:
                    party_assignments[txn["id"]] = {"customer_id": c["id"]}
                    break

    logger.info("match_party: matched %d of %d pending", len(party_assignments), len(pending))
    return {"party_assignments": party_assignments}

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


def persist(state: CategorizationState) -> dict:
    assignments = state["assignments"]
    party_assignments = state.get("party_assignments") or {}

    touched_ids = set(assignments.keys()) | set(party_assignments.keys())
    if not touched_ids:
        logger.info("persist: nothing to write")
        return {}

    with session_scope() as db:
        txns = (
            db.query(Transaction)
            .filter(Transaction.id.in_(touched_ids))
            .all()
        )
        for txn in txns:
            if txn.id in assignments:
                a = assignments[txn.id]
                txn.category_id = a["category_id"]
                txn.review_status = a["review_status"]
            if txn.id in party_assignments:
                p = party_assignments[txn.id]
                if "vendor_id" in p:
                    txn.vendor_id = p["vendor_id"]
                if "customer_id" in p:
                    txn.customer_id = p["customer_id"]

    logger.info(
        "persist: %d category updates, %d party updates",
        len(assignments), len(party_assignments),
    )
    return {}