"""transition_transaction — a WRITE tool: approve / reject / reclassify an
accounting transaction.

Write tools are "signal" tools: calling one does NOT mutate the database. It
returns a marker, and the graph routes into write_confirm (a human-in-the-loop
interrupt). Only after the user confirms does write_execute call `execute_*`
here to perform the change. This mirrors the chart_confirm pattern and keeps
financial writes from ever happening silently inside the agent loop.
"""

from datetime import datetime

from langchain.tools import tool

from app.infrastructure.db.database import SessionLocal, session_scope
from app.domain.models.ledger import Transaction, Account
from app.domain.enums import TransactionStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

ACTIONS = ("approve", "reject", "reclassify")


@tool
def transition_transaction(transaction_id: int, action: str, target_account_code: str = "") -> str:
    """Approve, reject, or reclassify an accounting transaction. This is a WRITE
    and will pause for the user to confirm before it commits — never assume it is
    already done.

    Args:
        transaction_id: the transaction to act on
        action: 'approve' | 'reject' | 'reclassify'
        target_account_code: required only for 'reclassify' — the posting-leaf
            account_code to move the categorized line to (e.g. '6200')
    """
    return "write_pending_confirmation"


def summarize_transition(business_id: int, args: dict) -> str:
    """Human-readable one-liner for the confirmation dialog."""
    tid = args.get("transaction_id")
    action = args.get("action")
    target = args.get("target_account_code")
    db = SessionLocal()
    try:
        t = (db.query(Transaction)
             .filter(Transaction.id == tid, Transaction.business_id == business_id).first())
        if t is None:
            return f"Transaction #{tid} not found."
        summary = f"{action} transaction #{t.id} '{t.name}' (currently {t.status.value})"
        if action == "reclassify" and target:
            acct = (db.query(Account)
                    .filter(Account.business_id == business_id,
                            Account.account_code == target).first())
            summary += f" -> account {target} {acct.account_name if acct else '(not found)'}"
        return summary
    finally:
        db.close()


def execute_transition(business_id: int, args: dict) -> str:
    """Perform the transition inside a committing session. Called by write_execute
    only after the user has confirmed."""
    tid = args["transaction_id"]
    action = args["action"]
    target = args.get("target_account_code")

    if action not in ACTIONS:
        return f"Unknown action '{action}'."

    with session_scope() as db:
        t = (db.query(Transaction)
             .filter(Transaction.id == tid, Transaction.business_id == business_id).first())
        if t is None:
            return f"Transaction #{tid} not found."

        if action == "reject":
            t.status = TransactionStatus.REJECTED
            t.reviewed_by, t.reviewed_at = "user", datetime.utcnow()
            logger.info("[write] transaction %s rejected", tid)
            return f"Transaction #{tid} rejected."

        if action == "reclassify":
            if not target:
                return "reclassify requires target_account_code."
            acct = (db.query(Account)
                    .filter(Account.business_id == business_id,
                            Account.account_code == target,
                            Account.posting_allowed.is_(True)).first())
            if acct is None:
                return f"Account {target} not found or not a posting leaf."
            # The cash line matches the source bank row's account; the OTHER entry
            # is the categorized line to move.
            cash_account_id = t.bank_transaction.account_id if t.bank_transaction else None
            categorized = next((e for e in t.entries if e.account_id != cash_account_id), None)
            if categorized is None:
                return "Could not identify the categorized entry to reclassify."
            categorized.account_id = acct.id
            t.status = TransactionStatus.APPROVED
            t.reviewed_by, t.reviewed_at = "user", datetime.utcnow()
            logger.info("[write] transaction %s reclassified to %s", tid, target)
            return f"Transaction #{tid} reclassified to {target} ({acct.account_name}) and approved."

        # approve
        t.status = TransactionStatus.APPROVED
        t.reviewed_by, t.reviewed_at = "user", datetime.utcnow()
        logger.info("[write] transaction %s approved", tid)
        return f"Transaction #{tid} approved."
