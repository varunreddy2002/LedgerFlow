"""DB-backed integration tests for posting, the pipeline, and the review queue.

These run against a real Postgres transaction (rolled back afterwards) so they
exercise the SQLAlchemy repositories, CHECK constraints, and end-to-end flow. They
skip automatically if Postgres is unreachable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import (
    ApprovalDecision,
    BankTxnStatus,
    JournalEntryStatus,
    ReviewItemType,
    ReviewStatus,
)
from app.domain.models.ledger import AccountingRule, BankTransaction, JournalEntry
from app.application.accounting.journal_entry_builder import AccountCatalog, JournalEntryBuilder
from app.application.accounting.ledger import LedgerService
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import SqlAlchemyLedgerRepository
from app.application.accounting.escalation.pipeline import build_pipeline
from app.application.accounting.review.dtos import ReviewResolution
from app.application.accounting.review.service import build_review_service

YEAR_START = date(2026, 1, 1)
YEAR_END = date(2026, 12, 31)


def _catalog(session, business_id) -> AccountCatalog:
    repo = SqlAlchemyLedgerRepository(session)
    return AccountCatalog.from_records(repo.list_accounts(business_id))


# ── Task 4: PostingService — POSTED-only visibility ─────────────────────────
def test_proposed_draft_is_invisible_to_reports(db_session, seeded_business):
    biz = seeded_business
    ledger = LedgerService(SqlAlchemyLedgerRepository(db_session))
    before = ledger.pnl(biz, YEAR_START, YEAR_END).total_expenses

    catalog = _catalog(db_session, biz)
    posting = PostingService(db_session)
    draft = (
        JournalEntryBuilder(catalog, biz, date(2026, 6, 1), description="pending hosting")
        .debit("5330", "100.00")
        .credit("1110", "100.00")
        .build()
    )
    entry = posting.propose(draft)   # PENDING_APPROVAL, not posted
    assert entry.status is JournalEntryStatus.PENDING_APPROVAL

    after = ledger.pnl(biz, YEAR_START, YEAR_END).total_expenses
    assert after == before  # a proposal never moves the books


def test_post_makes_entry_visible_and_keeps_books_balanced(db_session, seeded_business):
    biz = seeded_business
    ledger = LedgerService(SqlAlchemyLedgerRepository(db_session))
    before = ledger.pnl(biz, YEAR_START, YEAR_END).total_expenses

    catalog = _catalog(db_session, biz)
    posting = PostingService(db_session)
    draft = (
        JournalEntryBuilder(catalog, biz, date(2026, 6, 1), description="posted hosting")
        .debit("5330", "100.00")
        .credit("1110", "100.00")
        .build()
    )
    entry = posting.post(draft)
    assert entry.status is JournalEntryStatus.POSTED
    assert entry.entry_number  # generated

    after = ledger.pnl(biz, YEAR_START, YEAR_END).total_expenses
    assert after == before + Decimal("100.00")
    assert ledger.trial_balance(biz, YEAR_END).is_balanced


# ── Task 5: pipeline splits seeded bank rows correctly ──────────────────────
def test_pipeline_splits_bank_rows(db_session, seeded_business):
    biz = seeded_business
    pipeline = build_pipeline(db_session, biz)   # no classifier → deterministic
    outcomes = pipeline.run()

    posted = [o for o in outcomes if o.outcome == "posted"]
    review = [o for o in outcomes if o.outcome == "review"]
    # Seeded rows: AWS, GitHub, Stripe, Wire fee auto-post (4);
    # ADP payroll (large), Riverside, Nimbus → review (3).
    assert len(posted) == 4
    assert len(review) == 3

    item_types = sorted(o.item_type for o in review)
    assert item_types == [
        ReviewItemType.LARGE_AMOUNT.value,
        ReviewItemType.UNCATEGORIZED.value,
        ReviewItemType.UNCATEGORIZED.value,
    ]

    # Auto-posted rows are marked POSTED and linked to a journal entry.
    posted_bank = (
        db_session.query(BankTransaction)
        .filter(BankTransaction.business_id == biz, BankTransaction.status == BankTxnStatus.POSTED)
        .all()
    )
    assert len(posted_bank) == 4
    assert all(b.journal_entry_id is not None for b in posted_bank)


def test_pipeline_large_amount_never_posts(db_session, seeded_business):
    biz = seeded_business
    build_pipeline(db_session, biz).run()
    review_service = build_review_service(db_session, biz)
    large = review_service.list(item_type=ReviewItemType.LARGE_AMOUNT)
    assert len(large) == 1
    # The ADP row still carries its rule proposal, but was not auto-posted.
    assert large[0].proposed_account_code == "5210"   # Salaries and Wages
    adp = (
        db_session.query(BankTransaction)
        .filter(
            BankTransaction.business_id == biz,
            BankTransaction.external_transaction_id == "BNK-1005",
        )
        .one()
    )
    assert adp.status is BankTxnStatus.PROPOSED
    assert adp.journal_entry_id is None


# ── Task 6: resolving an uncategorized item posts + learns ──────────────────
def test_resolve_uncategorized_posts_entry_and_learns_rule(db_session, seeded_business):
    biz = seeded_business
    build_pipeline(db_session, biz).run()
    ledger = LedgerService(SqlAlchemyLedgerRepository(db_session))
    review_service = build_review_service(db_session, biz)

    uncategorized = review_service.list(item_type=ReviewItemType.UNCATEGORIZED)
    assert uncategorized  # Riverside + Nimbus
    target = next(v for v in uncategorized if v.description.startswith("Riverside"))

    rules_before = db_session.query(AccountingRule).filter(AccountingRule.business_id == biz).count()
    office_before = ledger.balance(biz, "5410")

    result = review_service.resolve(
        target.id,
        ReviewResolution(
            decision=ApprovalDecision.MODIFIED,
            account_code="5410",           # human files it under Office Rent
            actor="owner",
            notes="monthly office rent",
        ),
    )

    assert result.status == "resolved"
    assert result.journal_entry_id is not None
    assert result.rule_created is True

    # The entry is POSTED and the expense balance moved by the bank row's amount.
    entry = db_session.get(JournalEntry, result.journal_entry_id)
    assert entry.status is JournalEntryStatus.POSTED
    assert ledger.balance(biz, "5410") == office_before + Decimal("2200.00")
    assert ledger.trial_balance(biz, YEAR_END).is_balanced

    # The review item is resolved and a learned rule was added (the flywheel).
    resolved = review_service.list(status=ReviewStatus.RESOLVED, item_type=ReviewItemType.UNCATEGORIZED)
    assert any(v.id == target.id for v in resolved)
    rules_after = db_session.query(AccountingRule).filter(AccountingRule.business_id == biz).count()
    assert rules_after == rules_before + 1


def test_resolve_large_amount_posts_to_proposed_account(db_session, seeded_business):
    biz = seeded_business
    build_pipeline(db_session, biz).run()
    review_service = build_review_service(db_session, biz)
    ledger = LedgerService(SqlAlchemyLedgerRepository(db_session))

    large = review_service.list(item_type=ReviewItemType.LARGE_AMOUNT)[0]
    payroll_before = ledger.balance(biz, "5210")

    result = review_service.resolve(
        large.id, ReviewResolution(decision=ApprovalDecision.APPROVED, actor="owner"),
    )
    assert result.status == "resolved"
    assert ledger.balance(biz, "5210") == payroll_before + Decimal("12000.00")


def test_resolve_missing_item_raises(db_session, seeded_business):
    from app.application.accounting.errors import ReviewItemNotFoundError

    service = build_review_service(db_session, seeded_business)
    with pytest.raises(ReviewItemNotFoundError):
        service.resolve(999999, ReviewResolution(decision=ApprovalDecision.APPROVED))


def test_double_resolve_raises(db_session, seeded_business):
    from app.application.accounting.errors import ReviewItemAlreadyResolvedError

    biz = seeded_business
    build_pipeline(db_session, biz).run()
    service = build_review_service(db_session, biz)
    item = service.list(item_type=ReviewItemType.LARGE_AMOUNT)[0]
    service.resolve(item.id, ReviewResolution(decision=ApprovalDecision.APPROVED, actor="owner"))
    with pytest.raises(ReviewItemAlreadyResolvedError):
        service.resolve(item.id, ReviewResolution(decision=ApprovalDecision.APPROVED, actor="owner"))
