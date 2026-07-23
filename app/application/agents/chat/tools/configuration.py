"""manage_configuration — a WRITE tool: create or deactivate a categorization
rule. Same signal-then-confirm pattern as transition_transaction.

This is the *proper home* for "learned" accounting facts (e.g. "vendor Acme →
Office Supplies"): they become a real accounting_rules row the categorization
engine reuses — never fuzzy agent memory. Rule rows match the shape the
categorization engine understands (conditions: regex on normalized_description;
actions: account_code + confidence).
"""

from langchain.tools import tool
from sqlalchemy import func

from app.infrastructure.db.database import SessionLocal, session_scope
from app.domain.models.ledger import AccountingRule, Account
from app.domain.enums import RuleStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

OPERATIONS = ("create_rule", "deactivate_rule")


@tool
def manage_configuration(
    operation: str,
    rule_name: str = "",
    keyword: str = "",
    account_code: str = "",
    confidence: float = 0.8,
    rule_id: int = 0,
) -> str:
    """Create or deactivate a categorization rule. This is a WRITE and will pause
    for the user to confirm before it commits.

    Args:
        operation: 'create_rule' | 'deactivate_rule'
        rule_name: (create) a short name for the rule
        keyword: (create) text/regex to match against a bank row's description
            (e.g. 'stripe', 'aws')
        account_code: (create) the posting-leaf account_code matches route to
        confidence: (create) 0.0–1.0; >= 0.75 auto-approves future matches
        rule_id: (deactivate) the rule to deactivate
    """
    return "write_pending_confirmation"


def summarize_configuration(business_id: int, args: dict) -> str:
    op = args.get("operation")
    if op == "create_rule":
        return (f"create rule '{args.get('rule_name')}': match '{args.get('keyword')}' "
                f"-> account {args.get('account_code')} (confidence {args.get('confidence', 0.8)})")
    if op == "deactivate_rule":
        rid = args.get("rule_id")
        db = SessionLocal()
        try:
            r = (db.query(AccountingRule)
                 .filter(AccountingRule.id == rid, AccountingRule.business_id == business_id).first())
            return f"deactivate rule #{rid} '{r.rule_name}'" if r else f"deactivate rule #{rid} (not found)"
        finally:
            db.close()
    return f"unknown operation '{op}'"


def execute_configuration(business_id: int, args: dict) -> str:
    op = args.get("operation")
    if op not in OPERATIONS:
        return f"Unknown operation '{op}'."

    with session_scope() as db:
        if op == "create_rule":
            code = args.get("account_code")
            acct = (db.query(Account)
                    .filter(Account.business_id == business_id,
                            Account.account_code == code,
                            Account.posting_allowed.is_(True)).first())
            if acct is None:
                return f"Account {code} not found or not a posting leaf."
            if not args.get("keyword") or not args.get("rule_name"):
                return "create_rule requires rule_name and keyword."
            max_priority = (db.query(func.max(AccountingRule.priority))
                            .filter(AccountingRule.business_id == business_id).scalar() or 0)
            rule = AccountingRule(
                business_id=business_id,
                rule_name=args["rule_name"],
                rule_type="description",
                conditions={"field": "normalized_description", "operator": "regex",
                            "value": args["keyword"]},
                actions={"account_code": code, "confidence": float(args.get("confidence") or 0.8)},
                priority=max_priority + 1,
                status=RuleStatus.ACTIVE,
                created_by="user",
            )
            db.add(rule)
            db.flush()
            logger.info("[write] accounting_rule %s created", rule.id)
            return (f"Rule '{rule.rule_name}' created (#{rule.id}): '{args['keyword']}' "
                    f"-> {code} ({acct.account_name}).")

        # deactivate_rule
        rid = args.get("rule_id")
        r = (db.query(AccountingRule)
             .filter(AccountingRule.id == rid, AccountingRule.business_id == business_id).first())
        if r is None:
            return f"Rule #{rid} not found."
        r.status = RuleStatus.INACTIVE
        logger.info("[write] accounting_rule %s deactivated", rid)
        return f"Rule #{rid} '{r.rule_name}' deactivated."
