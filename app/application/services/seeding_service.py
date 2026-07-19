"""Seed a business with a working double-entry starting point.

Populates, idempotently, four things:

1. a full 3-level consulting **chart of accounts** (posting only at level-3 leaves);
2. deterministic **accounting_rules** (JSONB) mapping vendor/description keywords to
   posting accounts — the deterministic layer of the escalation ladder;
3. a handful of **POSTED journal entries** so P&L has data on day one;
4. **UNPROCESSED bank_transactions** that feed the ladder demo — some match rules,
   some don't, and one exceeds ``large_transaction_threshold``.

COA conventions (all *derived* from the tree so data can't drift):

* ``hierarchy_level`` — depth in the tree (1 = type header, 2 = group, 3 = leaf).
* ``posting_allowed`` — true iff the node is a leaf, unless overridden (e.g. the
  calculated ``3320 Current-Year Earnings`` leaf is not directly postable).
* ``account_subtype`` — a functional role declared once on each **level-2 group** and
  inherited by its leaves (``CASH``, ``RECEIVABLE``, ``PREPAID_ASSET`` …). Level-1
  headers carry no subtype.
* ``normal_balance`` — debit for assets/expenses, credit otherwise, **except** contra
  accounts (e.g. ``1500 Accumulated Depreciation``, a CONTRA_ASSET) which are credit
  normal; the deviation is declared on the group and inherited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import AccountType, NormalBalance
from app.domain.models.ledger import Account, AccountingRule, BankTransaction
from app.application.accounting.journal_entry_builder import (
    AccountCatalog,
    JournalEntryBuilder,
)
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import SqlAlchemyLedgerRepository

logger = get_logger(__name__)


# ── COA declaration ─────────────────────────────────────────────────────────
@dataclass
class _CoaNode:
    code: str
    name: str
    account_type: AccountType
    subtype: Optional[str] = None
    is_control: bool = False
    normal_balance: Optional[NormalBalance] = None   # override; None = derive from type
    posting: Optional[bool] = None                   # override; None = leaf iff no children
    children: List["_CoaNode"] = field(default_factory=list)


def _n(code, name, atype, *, subtype=None, is_control=False, normal_balance=None,
       posting=None, children=()) -> _CoaNode:
    return _CoaNode(code, name, atype, subtype, is_control, normal_balance, posting, list(children))


A, L, E, R, X = (
    AccountType.ASSET,
    AccountType.LIABILITY,
    AccountType.EQUITY,
    AccountType.REVENUE,
    AccountType.EXPENSE,
)
CR = NormalBalance.CREDIT

# 3-level consulting chart of accounts. Level 1 = type header, level 2 = reporting
# group (owns the subtype role), level 3 = posting leaf (inherits it).
CHART_OF_ACCOUNTS: List[_CoaNode] = [
    # ── Assets ──────────────────────────────────────────────────────────────
    _n("1000", "Assets", A, children=[
        _n("1100", "Cash and Cash Equivalents", A, subtype="CASH", children=[
            _n("1110", "Operating Checking", A),
            _n("1120", "Business Savings", A),
            _n("1130", "Petty Cash", A),
        ]),
        _n("1200", "Accounts Receivable", A, subtype="RECEIVABLE", children=[
            _n("1210", "Trade Accounts Receivable", A, is_control=True),
            _n("1220", "Employee Receivables", A),
        ]),
        _n("1300", "Prepaid Expenses", A, subtype="PREPAID_ASSET", children=[
            _n("1310", "Prepaid Insurance", A),
            _n("1320", "Prepaid Software", A),
            _n("1330", "Prepaid Rent", A),
        ]),
        _n("1400", "Fixed Assets", A, subtype="FIXED_ASSET", children=[
            _n("1410", "Computer Equipment", A),
            _n("1420", "Office Furniture", A),
            _n("1430", "Leasehold Improvements", A),
        ]),
        # Contra-asset: classified under assets but CREDIT normal (reduces assets).
        _n("1500", "Accumulated Depreciation", A, subtype="CONTRA_ASSET", normal_balance=CR, children=[
            _n("1510", "Accumulated Depreciation - Computers", A),
            _n("1520", "Accumulated Depreciation - Furniture", A),
        ]),
    ]),
    # ── Liabilities ─────────────────────────────────────────────────────────
    _n("2000", "Liabilities", L, children=[
        _n("2100", "Accounts Payable", L, subtype="PAYABLE", children=[
            _n("2110", "Trade Accounts Payable", L, is_control=True),
        ]),
        _n("2200", "Credit Cards", L, subtype="CREDIT_CARD", children=[
            _n("2210", "Business Credit Card", L),
        ]),
        _n("2300", "Taxes Payable", L, subtype="TAX_PAYABLE", children=[
            _n("2310", "Payroll Tax Payable", L),
            _n("2320", "Sales Tax Payable", L),
            _n("2330", "Income Tax Payable", L),
        ]),
        _n("2400", "Loans Payable", L, subtype="LOAN", children=[
            _n("2410", "Business Loan Payable", L),
            _n("2420", "Vehicle Loan Payable", L),
        ]),
        _n("2500", "Accrued Liabilities", L, subtype="ACCRUED_LIABILITY", children=[
            _n("2510", "Accrued Payroll", L),
            _n("2520", "Accrued Professional Fees", L),
            _n("2530", "Accrued Operating Expenses", L),
        ]),
        _n("2600", "Deferred Revenue", L, subtype="DEFERRED_REVENUE", children=[
            _n("2610", "Customer Deposits", L),
            _n("2620", "Unearned Consulting Revenue", L),
        ]),
    ]),
    # ── Equity ──────────────────────────────────────────────────────────────
    _n("3000", "Equity", E, children=[
        _n("3100", "Owner Capital", E, subtype="OWNER_CAPITAL", children=[
            _n("3110", "Owner Contributions", E),
        ]),
        _n("3200", "Owner Distributions", E, subtype="OWNER_DISTRIBUTION", children=[
            _n("3210", "Owner Draws", E),
        ]),
        _n("3300", "Retained Earnings", E, subtype="RETAINED_EARNINGS", children=[
            _n("3310", "Retained Earnings", E),
            # Current-year earnings is computed from P&L, never posted directly.
            _n("3320", "Current-Year Earnings", E, posting=False),
        ]),
    ]),
    # ── Revenue ─────────────────────────────────────────────────────────────
    _n("4000", "Revenue", R, children=[
        _n("4100", "Consulting Revenue", R, subtype="CONSULTING_REVENUE", children=[
            _n("4110", "Technology Consulting Revenue", R),
            _n("4120", "Business Consulting Revenue", R),
            _n("4130", "AI Consulting Revenue", R),
        ]),
        _n("4200", "Project Revenue", R, subtype="PROJECT_REVENUE", children=[
            _n("4210", "Fixed-Price Project Revenue", R),
            _n("4220", "Time-and-Materials Revenue", R),
        ]),
        _n("4300", "Training and Support Revenue", R, subtype="SUPPORT_REVENUE", children=[
            _n("4310", "Training Revenue", R),
            _n("4320", "Support and Maintenance Revenue", R),
        ]),
        _n("4400", "Other Revenue", R, subtype="OTHER_REVENUE", children=[
            _n("4410", "Referral Revenue", R),
            _n("4420", "Other Operating Revenue", R),
        ]),
    ]),
    # ── Expenses ────────────────────────────────────────────────────────────
    _n("5000", "Expenses", X, children=[
        _n("5100", "Cost of Services", X, subtype="COST_OF_SERVICES", children=[
            _n("5110", "Delivery Contractor Expense", X),
            _n("5120", "Project-Specific Software", X),
            _n("5130", "Project Travel Expense", X),
        ]),
        _n("5200", "Payroll and People", X, subtype="PAYROLL", children=[
            _n("5210", "Salaries and Wages", X),
            _n("5220", "Employer Payroll Taxes", X),
            _n("5230", "Employee Benefits", X),
            _n("5240", "Recruiting Expense", X),
        ]),
        _n("5300", "Technology Expenses", X, subtype="TECHNOLOGY", children=[
            _n("5310", "Software Subscriptions", X),
            _n("5320", "Cloud Hosting", X),
            _n("5330", "Internet and Communications", X),
            _n("5340", "Computer Support and Maintenance", X),
        ]),
        _n("5400", "Office and Administrative", X, subtype="OFFICE_ADMIN", children=[
            _n("5410", "Office Rent", X),
            _n("5420", "Utilities", X),
            _n("5430", "Office Supplies", X),
            _n("5440", "Postage and Shipping", X),
        ]),
        _n("5500", "Sales and Marketing", X, subtype="MARKETING", children=[
            _n("5510", "Advertising Expense", X),
            _n("5520", "Business Development", X),
            _n("5530", "Client Entertainment", X),
            _n("5540", "Website and Marketing Tools", X),
        ]),
        _n("5600", "Professional Services", X, subtype="PROFESSIONAL_SERVICES", children=[
            _n("5610", "Accounting Fees", X),
            _n("5620", "Legal Fees", X),
            _n("5630", "Consulting Fees", X),
            _n("5640", "Insurance Expense", X),
        ]),
        _n("5700", "Travel and Meals", X, subtype="TRAVEL_MEALS", children=[
            _n("5710", "Airfare", X),
            _n("5720", "Hotel Expense", X),
            _n("5730", "Ground Transportation", X),
            _n("5740", "Business Meals", X),
        ]),
        _n("5800", "Other Expenses", X, subtype="OTHER_EXPENSE", children=[
            _n("5810", "Bank Fees", X),
            _n("5820", "Merchant Processing Fees", X),
            _n("5830", "Interest Expense", X),
            _n("5840", "Depreciation Expense", X),
            _n("5850", "Licenses and Permits", X),
        ]),
    ]),
]


def _default_normal_balance(account_type: AccountType) -> NormalBalance:
    """Assets and expenses are debit-normal; everything else is credit-normal."""
    return (
        NormalBalance.DEBIT
        if account_type in (AccountType.ASSET, AccountType.EXPENSE)
        else NormalBalance.CREDIT
    )


def _resolve(getter) -> Dict[str, object]:
    """Walk the COA, resolving an inherited attribute for every account_code.

    ``getter(node)`` returns the node's own value or None; a None value inherits
    from the nearest ancestor that declared one. The single traversal shared by the
    subtype and normal-balance resolvers keeps them consistent.
    """
    resolved: Dict[str, object] = {}

    def rec(node: _CoaNode, inherited) -> None:
        own = getter(node)
        effective = own if own is not None else inherited
        resolved[node.code] = effective
        for child in node.children:
            rec(child, effective)

    for root in CHART_OF_ACCOUNTS:
        rec(root, None)
    return resolved


SUBTYPE_BY_CODE: Dict[str, Optional[str]] = _resolve(lambda n: n.subtype)
_NB_OVERRIDE_BY_CODE: Dict[str, Optional[NormalBalance]] = _resolve(lambda n: n.normal_balance)


def _normal_balance_for(node: _CoaNode) -> NormalBalance:
    override = _NB_OVERRIDE_BY_CODE.get(node.code)
    return override if override is not None else _default_normal_balance(node.account_type)


# ── Accounting rules (deterministic layer) ─────────────────────────────────
# (rule_name, description-regex, target account_code, confidence). Every target is
# a real posting leaf in the chart above. Money-in vs money-out is validated at
# posting time by direction consistency, so revenue and expense targets can coexist.
# Transfers, owner draws and taxes are intentionally NOT auto-classified — they must
# escalate to review rather than post to P&L on a guess.
RULE_SEED: List[Tuple[str, str, str, float]] = [
    # Revenue (money-in)
    ("Consulting revenue", r"stripe payout|stripe transfer|paypal|wise|bill\.com|client payment|invoice payment|consulting income", "4120", 0.75),
    ("Referral revenue", r"referral fee|referral payment|partner referral", "4410", 0.75),
    # Cost of services & payroll
    ("Delivery contractors", r"upwork|fiverr|toptal|contra|gun\.io|freelance|subcontractor|1099 contractor", "5110", 0.80),
    ("Payroll", r"gusto|rippling|adp|justworks|paychex|deel|payroll", "5210", 0.85),
    ("Employee benefits", r"health insurance premium|401k|benefits provider", "5230", 0.75),
    # Technology
    ("Software subscriptions", r"github|notion|figma|slack|zoom|openai|anthropic|linear|atlassian|dropbox|1password|adobe", "5310", 0.85),
    ("Cloud hosting", r"aws|amazon web services|google cloud|gcp|azure|cloudflare|digitalocean|heroku|vercel|render\.com", "5320", 0.85),
    ("Internet & communications", r"comcast|verizon|at&t|t-mobile|twilio|ringcentral|internet service|broadband", "5330", 0.80),
    ("Computer support", r"geek squad|it support|apple store|best buy|hardware repair", "5340", 0.70),
    # Office & administrative
    ("Office rent", r"wework|regus|coworking|office lease|office rent", "5410", 0.75),
    ("Utilities", r"pg&e|con edison|electric company|water district|gas company|utility bill", "5420", 0.75),
    ("Office supplies", r"staples|office depot|office supplies|stationery", "5430", 0.65),
    ("Postage & shipping", r"fedex|ups|usps|dhl|shipping|postage", "5440", 0.75),
    # Sales & marketing
    ("Advertising", r"google ads|linkedin ads|meta ads|facebook ads|advertising", "5510", 0.80),
    ("Marketing tools", r"hubspot|mailchimp|apollo|semrush|marketing platform", "5540", 0.75),
    # Professional services
    ("Accounting fees", r"accounting|quickbooks|xero|bookkeep|cpa", "5610", 0.80),
    ("Legal fees", r"legal|attorney|law firm|clio|counsel", "5620", 0.80),
    ("Insurance", r"insurance|hiscox|next insurance|liability coverage", "5640", 0.80),
    # Travel & meals
    ("Airfare", r"delta|united|american airlines|southwest|jetblue|alaska air|airfare|expedia flight", "5710", 0.75),
    ("Hotel", r"marriott|hilton|hyatt|airbnb|hotel|lodging", "5720", 0.75),
    ("Ground transportation", r"uber|lyft|taxi|hertz|avis|rental car", "5730", 0.75),
    ("Business meals", r"starbucks|restaurant|cafe|doordash|grubhub|uber eats|chipotle|business meal", "5740", 0.70),
    # Other expenses
    ("Bank fees", r"bank fee|wire fee|service charge|overdraft|monthly maintenance fee", "5810", 0.85),
    ("Merchant processing", r"stripe fee|square fee|processing fee|merchant fee|paypal fee", "5820", 0.85),
    ("Interest expense", r"interest charge|interest expense|loan interest|finance charge", "5830", 0.80),
    ("Licenses & permits", r"business license|permit|state filing|registration fee|annual report fee", "5850", 0.75),
]


# ── Sample POSTED journal entries (so P&L has data immediately) ─────────────
# (entry_date, amount, cash_movement, counter account_code, description)
_MONEY_IN = NormalBalance.DEBIT
_MONEY_OUT = NormalBalance.CREDIT
SAMPLE_ENTRIES: List[Tuple[date, str, NormalBalance, str, str]] = [
    (date(2026, 2, 10), "6000.00", _MONEY_IN, "4110", "Technology consulting - Acme Corp"),
    (date(2026, 2, 15), "3200.00", _MONEY_OUT, "5210", "Payroll run"),
    (date(2026, 3, 1), "500.00", _MONEY_OUT, "5310", "GitHub + Notion subscriptions"),
    (date(2026, 3, 20), "1200.00", _MONEY_OUT, "5710", "Client onsite - airfare"),
    (date(2026, 4, 5), "9000.00", _MONEY_IN, "4130", "AI consulting engagement - Globex"),
    (date(2026, 4, 18), "300.00", _MONEY_OUT, "5320", "AWS monthly usage"),
]


# ── Sample UNPROCESSED bank rows (feed the ladder demo) ─────────────────────
# (description, amount, cash_movement, external_id). Chosen so the ladder splits:
#   • rule match, high confidence, small → auto-posts
#   • rule match but over large_transaction_threshold → large_amount review
#   • no rule match → uncategorized review
SAMPLE_BANK_ROWS: List[Tuple[str, str, NormalBalance, str]] = [
    ("AWS cloud services", "42.00", _MONEY_OUT, "BNK-1001"),
    ("GitHub monthly plan", "21.00", _MONEY_OUT, "BNK-1002"),
    ("Stripe payout - client Northwind", "4800.00", _MONEY_IN, "BNK-1003"),
    ("Wire fee", "35.00", _MONEY_OUT, "BNK-1004"),
    ("ADP payroll run", "12000.00", _MONEY_OUT, "BNK-1005"),        # > threshold → large_amount
    ("Riverside Realty Holdings", "2200.00", _MONEY_OUT, "BNK-1006"),  # no rule → uncategorized
    ("Nimbus Data Systems", "850.00", _MONEY_OUT, "BNK-1007"),      # no rule → uncategorized
]

_CASH_ACCOUNT_CODE = "1110"  # Operating Checking — the bank rows' GL account


class BusinessSeeder:
    """Seeds one business's ledger starting point. Idempotent per section."""

    def __init__(self, session: Session, business_id: int) -> None:
        self._session = session
        self._business_id = business_id

    # ── public orchestration ────────────────────────────────────────────────
    def seed_all(self) -> None:
        created = self._seed_accounts()
        self._seed_rules()
        if created:
            # Only seed sample activity on a first-time setup, so re-running /setup
            # never double-posts entries or re-imports bank rows.
            self._seed_journal_entries()
            self._seed_bank_transactions()
        else:
            logger.info("[seed] accounts already present; skipping sample activity")

    # ── 1. chart of accounts ────────────────────────────────────────────────
    def _seed_accounts(self) -> bool:
        """Insert the COA tree if absent. Returns True if it created accounts."""
        existing = (
            self._session.query(Account.id)
            .filter(Account.business_id == self._business_id)
            .first()
        )
        if existing is not None:
            return False

        def walk(node: _CoaNode, parent_id: Optional[int], level: int) -> None:
            posting_allowed = node.posting if node.posting is not None else (not node.children)
            account = Account(
                business_id=self._business_id,
                account_code=node.code,
                account_name=node.name,
                account_type=node.account_type,
                account_subtype=SUBTYPE_BY_CODE.get(node.code),      # inherited from group
                parent_account_id=parent_id,
                hierarchy_level=level,
                normal_balance=_normal_balance_for(node),            # contra-aware
                posting_allowed=posting_allowed,
                is_control_account=node.is_control,
                is_active=True,
            )
            self._session.add(account)
            self._session.flush()  # assign id for children
            for child in node.children:
                walk(child, account.id, level + 1)

        for root in CHART_OF_ACCOUNTS:
            walk(root, None, 1)
        self._session.flush()
        logger.info("[seed] chart of accounts created for business_id=%s", self._business_id)
        return True

    # ── 2. accounting rules ─────────────────────────────────────────────────
    def _seed_rules(self) -> None:
        existing = {
            name
            for (name,) in self._session.query(AccountingRule.rule_name).filter(
                AccountingRule.business_id == self._business_id
            )
        }
        added = 0
        for priority, (name, pattern, code, confidence) in enumerate(RULE_SEED, start=10):
            if name in existing:
                continue
            self._session.add(AccountingRule(
                business_id=self._business_id,
                rule_name=name,
                rule_type="description",
                conditions={"match_field": "description", "op": "regex", "value": pattern},
                actions={"account_code": code, "confidence": confidence},
                priority=priority,
                is_system=True,
                is_active=True,
            ))
            added += 1
        if added:
            self._session.flush()
            logger.info("[seed] %d accounting rules seeded for business_id=%s",
                        added, self._business_id)

    # ── 3. sample posted journal entries ────────────────────────────────────
    def _seed_journal_entries(self) -> None:
        catalog = self._catalog()
        posting = PostingService(self._session)
        for entry_date, amount, movement, counter_code, description in SAMPLE_ENTRIES:
            draft = JournalEntryBuilder.from_bank_movement(
                catalog,
                business_id=self._business_id,
                entry_date=entry_date,
                cash_account_ref=_CASH_ACCOUNT_CODE,
                counter_account_ref=counter_code,
                amount=amount,
                cash_movement=movement,
                description=description,
            )
            posting.post(draft, decided_by="seed", notes="seeded sample entry")
        logger.info("[seed] %d sample journal entries posted for business_id=%s",
                    len(SAMPLE_ENTRIES), self._business_id)

    # ── 4. sample unprocessed bank rows ─────────────────────────────────────
    def _seed_bank_transactions(self) -> None:
        gl_account_id = self._account_id(_CASH_ACCOUNT_CODE)
        for description, amount, movement, external_id in SAMPLE_BANK_ROWS:
            self._session.add(BankTransaction(
                business_id=self._business_id,
                gl_account_id=gl_account_id,
                external_transaction_id=external_id,
                transaction_date=date(2026, 5, 1),
                description=description,
                normalized_description=description.lower(),
                amount=Decimal(amount),
                cash_movement=movement,
                currency="USD",
            ))
        self._session.flush()
        logger.info("[seed] %d sample bank rows imported for business_id=%s",
                    len(SAMPLE_BANK_ROWS), self._business_id)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _catalog(self) -> AccountCatalog:
        repo = SqlAlchemyLedgerRepository(self._session)
        return AccountCatalog.from_records(repo.list_accounts(self._business_id))

    def _account_id(self, code: str) -> int:
        account = (
            self._session.query(Account)
            .filter(Account.business_id == self._business_id, Account.account_code == code)
            .one()
        )
        return account.id


def seed_business_defaults(db: Session, business_id: int) -> None:
    """Seed a business's COA, rules, sample entries and bank rows (idempotent)."""
    BusinessSeeder(db, business_id).seed_all()


def backfill_account_subtypes(db: Session, business_id: int) -> int:
    """Re-derive account_subtype for every existing account from the COA hierarchy.

    Fixes rows seeded before the inheritance rule existed (level-2 group role
    inherited by its leaves; level-1 headers = None). Idempotent; returns the number
    of rows changed. Leaves journal entries / bank rows untouched.
    """
    changed = 0
    accounts = db.query(Account).filter(Account.business_id == business_id).all()
    for account in accounts:
        expected = SUBTYPE_BY_CODE.get(account.account_code)
        if account.account_subtype != expected:
            account.account_subtype = expected
            changed += 1
    db.flush()
    logger.info("[seed] backfilled account_subtype for %d rows (business_id=%s)",
                changed, business_id)
    return changed
