"""Unit tests for JournalEntryBuilder — the posting invariants.

No database: the builder validates against an in-memory :class:`AccountCatalog`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import NormalBalance
from app.application.accounting.errors import (
    DirectionConsistencyError,
    EmptyJournalEntryError,
    PostingToNonLeafError,
    UnbalancedEntryError,
)
from app.application.accounting.journal_entry_builder import (
    AccountCatalog,
    JournalEntryBuilder,
)
from tests.accounting.factories import sample_accounts

ENTRY_DATE = date(2026, 6, 1)


@pytest.fixture
def catalog() -> AccountCatalog:
    return AccountCatalog.from_records(sample_accounts())


def test_balanced_entry_builds(catalog: AccountCatalog):
    draft = (
        JournalEntryBuilder(catalog, 1, ENTRY_DATE, description="hosting")
        .debit("5320", "42.00", reason_code="rule:aws")
        .credit("1110", "42.00")
        .build()
    )
    assert len(draft.lines) == 2
    assert draft.total_debit == draft.total_credit == Decimal("42.00")
    assert draft.lines[0].reason_code == "rule:aws"


def test_unbalanced_entry_raises(catalog: AccountCatalog):
    with pytest.raises(UnbalancedEntryError) as exc:
        (
            JournalEntryBuilder(catalog, 1, ENTRY_DATE)
            .debit("5320", "42.00")
            .credit("1110", "40.00")
            .build()
        )
    assert exc.value.total_debit == Decimal("42.00")
    assert exc.value.total_credit == Decimal("40.00")


def test_posting_to_non_leaf_raises(catalog: AccountCatalog):
    # 5000 Expenses is a level-1 header, posting_allowed=False.
    with pytest.raises(PostingToNonLeafError):
        JournalEntryBuilder(catalog, 1, ENTRY_DATE).debit("5000", "10.00")


def test_empty_entry_raises(catalog: AccountCatalog):
    with pytest.raises(EmptyJournalEntryError):
        JournalEntryBuilder(catalog, 1, ENTRY_DATE).build()


def test_amounts_are_quantized(catalog: AccountCatalog):
    draft = (
        JournalEntryBuilder(catalog, 1, ENTRY_DATE)
        .debit("5320", 19.9)
        .credit("1110", 19.9)
        .build()
    )
    assert draft.lines[0].debit_amount == Decimal("19.90")


# ── from_bank_movement (owner-confirmed cash-basis rules) ──────────────────
def test_money_in_debits_cash_credits_revenue(catalog: AccountCatalog):
    draft = JournalEntryBuilder.from_bank_movement(
        catalog, business_id=1, entry_date=ENTRY_DATE,
        cash_account_ref="1110", counter_account_ref="4110",
        amount="1000.00", cash_movement=NormalBalance.DEBIT,
        description="client deposit",
    )
    by_code = {ln.account_code: ln for ln in draft.lines}
    assert by_code["1110"].debit_amount == Decimal("1000.00")
    assert by_code["4110"].credit_amount == Decimal("1000.00")


def test_money_out_credits_cash_debits_expense(catalog: AccountCatalog):
    draft = JournalEntryBuilder.from_bank_movement(
        catalog, business_id=1, entry_date=ENTRY_DATE,
        cash_account_ref="1110", counter_account_ref="5320",
        amount="200.00", cash_movement=NormalBalance.CREDIT,
        description="aws",
    )
    by_code = {ln.account_code: ln for ln in draft.lines}
    assert by_code["1110"].credit_amount == Decimal("200.00")
    assert by_code["5320"].debit_amount == Decimal("200.00")


def test_money_in_with_expense_counter_is_inconsistent(catalog: AccountCatalog):
    # Deposit (money-in) but counter is an expense → contradiction → escalate.
    with pytest.raises(DirectionConsistencyError):
        JournalEntryBuilder.from_bank_movement(
            catalog, business_id=1, entry_date=ENTRY_DATE,
            cash_account_ref="1110", counter_account_ref="5320",
            amount="50.00", cash_movement=NormalBalance.DEBIT,
        )


def test_money_out_with_revenue_counter_is_inconsistent(catalog: AccountCatalog):
    with pytest.raises(DirectionConsistencyError):
        JournalEntryBuilder.from_bank_movement(
            catalog, business_id=1, entry_date=ENTRY_DATE,
            cash_account_ref="1110", counter_account_ref="4110",
            amount="50.00", cash_movement=NormalBalance.CREDIT,
        )
