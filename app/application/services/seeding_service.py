"""Seed a business's chart of accounts and its deterministic accounting rules.

The COA below is the one worked out for a consulting-business MVP: fixed
3-level tree, 4 account types (equity lives under LIABILITY via
account_subtype='equity', not as its own type), purely cash-triggered
accounts only — no depreciation/prepaid/accrual machinery.

The rule set is a generic consulting-business baseline, meant to be tuned once
real bank statement wording is known. It deliberately does NOT cover every
account: Project/Training Revenue, Payroll Taxes, and loan payments can't be
told apart from a bank description alone (a naive keyword rule would produce a
confidently wrong answer, not just a missing one) — those stay unmatched,
falling through to manual review.

Sample activity (transactions, bank rows) isn't seeded here yet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domain.enums import AccountType, NormalBalance
from app.domain.models import Account, AccountingRule

logger = logging.getLogger(__name__)


@dataclass
class _CoaNode:
    code: str
    name: str
    account_type: AccountType
    subtype: Optional[str] = None
    normal_balance: Optional[NormalBalance] = None  # override; None = derive from type
    children: List["_CoaNode"] = field(default_factory=list)


def _n(code, name, atype, *, subtype=None, normal_balance=None, children=()) -> _CoaNode:
    return _CoaNode(code, name, atype, subtype, normal_balance, list(children))


A, L, R, X = (
    AccountType.ASSET,
    AccountType.LIABILITY,
    AccountType.REVENUE,
    AccountType.EXPENSE,
)
DR = NormalBalance.DEBIT

CHART_OF_ACCOUNTS: List[_CoaNode] = [
    _n("1000", "Assets", A, children=[
        _n("1100", "Cash and Bank", A, subtype="cash", children=[
            _n("1110", "Operating Checking", A),
            _n("1120", "Business Savings", A),
            _n("1130", "Petty Cash", A),
        ]),
        _n("1200", "Accounts Receivable", A, subtype="receivable", children=[
            _n("1210", "Accounts Receivable", A),
            _n("1220", "Employee Advances", A),
        ]),
    ]),
    _n("2000", "Liabilities", L, children=[
        _n("2100", "Accounts Payable", L, subtype="payable", children=[
            _n("2110", "Accounts Payable", L),
        ]),
        _n("2200", "Credit Cards", L, subtype="credit_card", children=[
            _n("2210", "Business Credit Card", L),
        ]),
        _n("2300", "Taxes Payable", L, subtype="tax_payable", children=[
            _n("2310", "Taxes Payable", L),
        ]),
        _n("2400", "Loans Payable", L, subtype="loan", children=[
            _n("2410", "Business Loan Payable", L),
            _n("2420", "Line of Credit Payable", L),
        ]),
        # Equity lives under LIABILITY via subtype, not as its own account_type.
        _n("2900", "Owner's Equity", L, subtype="equity", children=[
            _n("2910", "Owner Contributions", L),
            # Contra-equity: increases on the DEBIT side, opposite of its
            # credit-normal siblings (a draw reduces equity).
            _n("2920", "Owner Draws", L, normal_balance=DR),
            _n("2930", "Retained Earnings", L),
        ]),
    ]),
    _n("4000", "Revenue", R, children=[
        _n("4100", "Consulting Revenue", R, children=[
            _n("4110", "Consulting Fees", R),
        ]),
        _n("4200", "Project Revenue", R, children=[
            _n("4210", "Project Revenue", R),
        ]),
        _n("4300", "Training Revenue", R, children=[
            _n("4310", "Training & Workshop Revenue", R),
        ]),
        _n("4400", "Other Income", R, children=[
            _n("4410", "Reimbursed Client Expenses", R),
            _n("4420", "Interest Income", R),
        ]),
    ]),
    _n("5000", "Expenses", X, children=[
        _n("5100", "Contractors", X, children=[
            _n("5110", "Contractor Payments", X),
        ]),
        _n("5200", "Payroll", X, children=[
            _n("5210", "Salaries & Wages", X),
            _n("5220", "Payroll Taxes", X),
        ]),
        _n("5300", "Software & Technology", X, children=[
            _n("5310", "Software Subscriptions", X),
            _n("5320", "Cloud Hosting", X),
        ]),
        _n("5400", "Office & Admin", X, children=[
            _n("5410", "Rent / Coworking", X),
            _n("5420", "Utilities", X),
            _n("5430", "Office Supplies", X),
            _n("5440", "Postage & Shipping", X),
        ]),
        _n("5500", "Marketing", X, children=[
            _n("5510", "Advertising", X),
            _n("5520", "Website & Marketing Tools", X),
        ]),
        _n("5600", "Professional Fees", X, children=[
            _n("5610", "Accounting & Bookkeeping", X),
            _n("5620", "Legal Fees", X),
            _n("5630", "Business Insurance", X),
            _n("5640", "Professional Development", X),
            _n("5650", "Business Licenses & Permits", X),
        ]),
        _n("5700", "Travel & Meals", X, children=[
            _n("5710", "Airfare & Transportation", X),
            _n("5720", "Lodging", X),
            _n("5730", "Business Meals", X),
        ]),
        _n("5800", "Bank & Merchant Fees", X, children=[
            _n("5810", "Bank Fees", X),
            _n("5820", "Merchant Processing Fees", X),
            _n("5830", "Interest Expense", X),
        ]),
    ]),
]


# (rule_name, regex pattern, target account_code, confidence). Matched against
# bank_transactions.normalized_description. Every target is a real posting leaf
# in the chart above. Confidence threshold for auto-approval is 0.75, per the
# original CSV-pipeline convention — kept below that here means "stays
# NEEDS_REVIEW even on a match."
RULE_SEED: List[Tuple[str, str, str, float]] = [
    # Revenue — only the generic bucket; Project/Training Revenue need a
    # better signal than description text (see module docstring).
    ("Consulting revenue", r"stripe|paypal|wise|bill\.com|client payment|invoice payment|consulting fee", "4110", 0.75),
    ("Interest income", r"interest earned|interest income|interest payment received", "4420", 0.80),
    # Cost of delivery
    ("Contractor payments", r"upwork|fiverr|toptal|contra|gun\.io|freelance|1099 contractor", "5110", 0.80),
    ("Payroll", r"gusto|rippling|adp|justworks|paychex|deel|payroll run", "5210", 0.85),
    # Software & technology
    ("Software subscriptions", r"github|notion|figma|slack|zoom|openai|anthropic|linear|atlassian|dropbox|1password|adobe", "5310", 0.85),
    ("Cloud hosting", r"aws|amazon web services|google cloud|gcp|azure|cloudflare|digitalocean|heroku|vercel|render\.com", "5320", 0.85),
    # Office & admin
    ("Rent / coworking", r"wework|regus|coworking|office lease|office rent", "5410", 0.75),
    ("Utilities", r"electric company|water district|gas company|utility bill|pg&e|con edison", "5420", 0.75),
    ("Office supplies", r"staples|office depot|office supplies|stationery", "5430", 0.65),
    ("Postage & shipping", r"fedex|ups|usps|dhl|shipping|postage", "5440", 0.75),
    # Marketing
    ("Advertising", r"google ads|linkedin ads|meta ads|facebook ads", "5510", 0.80),
    ("Marketing tools", r"hubspot|mailchimp|squarespace|wordpress|semrush", "5520", 0.75),
    # Professional fees
    ("Accounting & bookkeeping", r"quickbooks|xero|bookkeep|cpa|accounting fee", "5610", 0.80),
    ("Legal fees", r"legal|attorney|law firm|clio", "5620", 0.80),
    ("Business insurance", r"insurance|hiscox|next insurance", "5630", 0.80),
    ("Professional development", r"udemy|coursera|pluralsight|conference|summit", "5640", 0.70),
    ("Licenses & permits", r"business license|state filing|registration fee|permit", "5650", 0.70),
    # Travel & meals
    ("Airfare & transportation", r"delta|united|american airlines|southwest|uber|lyft|taxi|rental car", "5710", 0.75),
    ("Lodging", r"marriott|hilton|hyatt|airbnb|hotel", "5720", 0.75),
    ("Business meals", r"starbucks|restaurant|cafe|doordash|grubhub|chipotle", "5730", 0.65),
    # Bank & merchant fees
    ("Bank fees", r"bank fee|wire fee|service charge|overdraft|monthly maintenance fee", "5810", 0.85),
    ("Merchant processing fees", r"stripe fee|square fee|processing fee|paypal fee", "5820", 0.85),
    ("Interest expense", r"loan interest|interest charge|finance charge", "5830", 0.75),
    # Owner activity (equity, not expense — still a valid rule target)
    ("Owner draws", r"owner draw|owner withdrawal|distribution|partner draw", "2920", 0.80),
    ("Owner contributions", r"owner contribution|capital contribution|owner deposit", "2910", 0.80),
    # Liability paydowns triggered by an outgoing bank payment
    ("Credit card payment", r"credit card payment|card payment thank you|cc payment", "2210", 0.70),
    ("Tax remittance", r"sales tax payment|dept of revenue|franchise tax board|state tax payment", "2310", 0.75),
    # Revenue-adjacent inflow that isn't a fee for services
    ("Reimbursed client expenses", r"reimbursement|expense reimbursement|travel reimbursement", "4410", 0.70),
]


def _default_normal_balance(account_type: AccountType) -> NormalBalance:
    return (
        NormalBalance.DEBIT
        if account_type in (AccountType.ASSET, AccountType.EXPENSE)
        else NormalBalance.CREDIT
    )


def _resolve_subtypes() -> Dict[str, Optional[str]]:
    """Level-2 groups declare a subtype; leaves inherit it from their parent."""
    resolved: Dict[str, Optional[str]] = {}

    def rec(n: _CoaNode, inherited: Optional[str]) -> None:
        effective = n.subtype if n.subtype is not None else inherited
        resolved[n.code] = effective
        for child in n.children:
            rec(child, effective)

    for root in CHART_OF_ACCOUNTS:
        rec(root, None)
    return resolved


def _seed_accounts(db: Session, business_id: int) -> None:
    """Idempotent — a no-op if accounts already exist for this business."""
    existing = db.query(Account.id).filter(Account.business_id == business_id).first()
    if existing is not None:
        logger.info("Accounts already seeded for business_id=%s, skipping", business_id)
        return

    subtype_by_code = _resolve_subtypes()
    created = 0

    def walk(node: _CoaNode, parent_id: Optional[int], level: int) -> None:
        nonlocal created
        normal_balance = node.normal_balance or _default_normal_balance(node.account_type)
        account = Account(
            business_id=business_id,
            account_code=node.code,
            account_name=node.name,
            account_type=node.account_type,
            account_subtype=subtype_by_code.get(node.code),
            parent_account_id=parent_id,
            hierarchy_level=level,
            normal_balance=normal_balance,
            posting_allowed=not node.children,
            is_active=True,
        )
        db.add(account)
        db.flush()  # assign id so children can reference it as parent_account_id
        created += 1
        for child in node.children:
            walk(child, account.id, level + 1)

    for root in CHART_OF_ACCOUNTS:
        walk(root, None, 1)

    logger.info("Seeded %d accounts for business_id=%s", created, business_id)


def _seed_accounting_rules(db: Session, business_id: int) -> None:
    """Idempotent per rule_name — safe to call again after RULE_SEED grows."""
    account_id_by_code: Dict[str, int] = {
        code: acct_id
        for code, acct_id in db.query(Account.account_code, Account.id).filter(
            Account.business_id == business_id,
        )
    }
    existing_names = {
        name for (name,) in db.query(AccountingRule.rule_name).filter(
            AccountingRule.business_id == business_id,
        )
    }

    created = 0
    for priority, (rule_name, pattern, account_code, confidence) in enumerate(RULE_SEED, start=10):
        if rule_name in existing_names:
            continue
        account_id = account_id_by_code.get(account_code)
        if account_id is None:
            logger.warning("Skipping rule %r: account_code %s not found", rule_name, account_code)
            continue
        db.add(AccountingRule(
            business_id=business_id,
            rule_name=rule_name,
            rule_type="description",
            conditions={"field": "normalized_description", "operator": "regex", "value": pattern},
            actions={"account_code": account_code, "confidence": confidence},
            priority=priority,
        ))
        created += 1

    if created:
        logger.info("Seeded %d accounting rules for business_id=%s", created, business_id)
    else:
        logger.info("Accounting rules already seeded for business_id=%s, skipping", business_id)


def seed_business_defaults(db: Session, business_id: int) -> None:
    """Seed accounts, then accounting rules. Each step is independently
    idempotent, so re-running after RULE_SEED grows adds only the new rules
    without re-seeding (or duplicating) accounts."""
    _seed_accounts(db, business_id)
    _seed_accounting_rules(db, business_id)
