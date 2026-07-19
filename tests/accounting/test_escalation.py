"""Unit tests for the deterministic escalation handlers (Chain of Responsibility).

No database: the chain runs with an in-memory catalog, fake posting service, and
fake repositories, so we assert routing decisions (auto-post vs. review) and the
large-amount override precisely.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import (
    EscalationSource,
    NormalBalance,
    ReviewItemType,
)
from app.application.accounting.journal_entry_builder import AccountCatalog
from app.application.accounting.rule_engine import AccountingRuleEngine, RuleSpec
from app.application.accounting.escalation.context import (
    LadderContext,
    NullAccountClassifier,
)
from app.application.accounting.escalation.handlers import (
    AgentHandler,
    RuleHandler,
    ReviewHandler,
)
from tests.accounting.factories import (
    FakeBankRepo,
    FakeBankTxn,
    FakePostingService,
    FakeReviewRepo,
    sample_accounts,
)

ENTRY_DATE = date(2026, 6, 1)
THRESHOLD = 0.75
LARGE = 5000.0

# Two rules: a high-confidence expense rule and a low-confidence one.
RULES = [
    RuleSpec(1, "Cloud hosting", "description", "regex", r"aws|cloud", "5320", 0.90, 10),
    RuleSpec(2, "Maybe office", "description", "regex", r"depot", "5610", 0.50, 20),
    RuleSpec(3, "Consulting revenue", "description", "regex", r"stripe", "4110", 0.80, 30),
]


def _build_chain(classifier=None, threshold=THRESHOLD, large=LARGE):
    catalog = AccountCatalog.from_records(sample_accounts())
    leaves = [r for r in sample_accounts() if r.posting_allowed]
    posting = FakePostingService()
    bank_repo = FakeBankRepo()
    review_repo = FakeReviewRepo()
    rule = RuleHandler(
        AccountingRuleEngine(RULES), catalog, posting, bank_repo,
        confidence_threshold=threshold, large_amount_threshold=large,
    )
    agent = AgentHandler(classifier or NullAccountClassifier(), catalog, leaves)
    review = ReviewHandler(review_repo, bank_repo)
    rule.set_next(agent).set_next(review)
    return rule, posting, bank_repo, review_repo


def _ctx(bank_repo, txn_id, description, amount, movement=NormalBalance.CREDIT):
    bank_repo.register(FakeBankTxn(txn_id))
    return LadderContext(
        bank_transaction_id=txn_id,
        business_id=1,
        cash_account_id=3,          # 1110 Operating Checking
        description=description,
        amount=Decimal(amount),
        cash_movement=movement,
        entry_date=ENTRY_DATE,
    )


def test_high_confidence_rule_auto_posts():
    head, posting, bank_repo, review_repo = _build_chain()
    ctx = _ctx(bank_repo, 101, "AWS cloud services", "42.00", NormalBalance.CREDIT)
    outcome = head.handle(ctx)

    assert outcome.outcome == "posted"
    assert outcome.account_code == "5320"
    assert len(posting.posted) == 1
    assert bank_repo.posted == [(101, posting.posted[0]["id"])]
    assert review_repo.items == []


def test_low_confidence_rule_goes_to_review_with_proposal():
    head, posting, bank_repo, review_repo = _build_chain()
    ctx = _ctx(bank_repo, 102, "Office Depot supplies", "60.00", NormalBalance.CREDIT)
    outcome = head.handle(ctx)

    assert outcome.outcome == "review"
    assert outcome.item_type == ReviewItemType.UNCATEGORIZED.value
    assert posting.posted == []                 # never posted below the gate
    item = review_repo.items[0]
    assert item.item_type is ReviewItemType.UNCATEGORIZED
    assert item.source is EscalationSource.RULE
    assert item.proposed_resolution["account_code"] == "5610"


def test_large_amount_overrides_high_confidence():
    head, posting, bank_repo, review_repo = _build_chain()
    ctx = _ctx(bank_repo, 103, "AWS reserved instances", "12000.00", NormalBalance.CREDIT)
    outcome = head.handle(ctx)

    assert outcome.outcome == "review"
    assert outcome.item_type == ReviewItemType.LARGE_AMOUNT.value
    assert posting.posted == []                 # large amounts never auto-post
    item = review_repo.items[0]
    assert item.item_type is ReviewItemType.LARGE_AMOUNT
    assert item.proposed_resolution["account_code"] == "5320"   # proposal preserved


def test_no_rule_match_goes_to_uncategorized_review():
    head, posting, bank_repo, review_repo = _build_chain()
    ctx = _ctx(bank_repo, 104, "Riverside Property Mgmt", "2200.00", NormalBalance.CREDIT)
    outcome = head.handle(ctx)

    assert outcome.outcome == "review"
    assert outcome.item_type == ReviewItemType.UNCATEGORIZED.value
    item = review_repo.items[0]
    assert item.source is EscalationSource.AGENT      # agent seam, no rule
    assert item.proposed_resolution is None           # null classifier defers
    assert bank_repo.proposed == [104]


def test_money_in_matching_revenue_rule_auto_posts():
    head, posting, bank_repo, review_repo = _build_chain()
    ctx = _ctx(bank_repo, 105, "Stripe payout", "480.00", NormalBalance.DEBIT)
    outcome = head.handle(ctx)

    assert outcome.outcome == "posted"
    assert outcome.account_code == "4110"
    # Money-in ⇒ Dr Cash / Cr Revenue; builder produced a balanced draft.
    draft = posting.posted[0]["draft"]
    assert draft.total_debit == draft.total_credit == Decimal("480.00")


def test_direction_conflict_escalates_instead_of_posting():
    # A money-IN row whose rule points at an EXPENSE account: cannot post cash-basis.
    conflicting_rules = [RuleSpec(9, "Bad", "description", "regex", r"weird", "5320", 0.95, 5)]
    catalog = AccountCatalog.from_records(sample_accounts())
    leaves = [r for r in sample_accounts() if r.posting_allowed]
    posting = FakePostingService()
    bank_repo = FakeBankRepo()
    review_repo = FakeReviewRepo()
    rule = RuleHandler(
        AccountingRuleEngine(conflicting_rules), catalog, posting, bank_repo,
        confidence_threshold=THRESHOLD, large_amount_threshold=LARGE,
    )
    rule.set_next(AgentHandler(NullAccountClassifier(), catalog, leaves)).set_next(
        ReviewHandler(review_repo, bank_repo)
    )
    bank_repo.register(FakeBankTxn(106))
    ctx = LadderContext(
        bank_transaction_id=106, business_id=1, cash_account_id=3,
        description="weird deposit", amount=Decimal("100.00"),
        cash_movement=NormalBalance.DEBIT, entry_date=ENTRY_DATE,
    )
    outcome = rule.handle(ctx)

    assert outcome.outcome == "review"          # direction conflict → review, not post
    assert posting.posted == []
