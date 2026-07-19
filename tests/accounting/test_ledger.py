"""Unit tests for LedgerService — sign convention, rollup, and balancing.

No database: the service runs against :class:`FakeLedgerRepository`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import AccountType, NormalBalance
from app.application.accounting.ledger import LedgerService
from app.application.accounting.repository import LineTotals
from tests.accounting.factories import (
    FakeLedgerRepository,
    sample_accounts,
    sample_totals,
)

START = date(2026, 1, 1)
END = date(2026, 12, 31)


@pytest.fixture
def ledger() -> LedgerService:
    return LedgerService(FakeLedgerRepository())


def test_signed_balance_debit_normal():
    totals = LineTotals(debit=Decimal("200"), credit=Decimal("50"))
    assert LedgerService._signed_balance(NormalBalance.DEBIT, totals) == Decimal("150")


def test_signed_balance_credit_normal():
    totals = LineTotals(debit=Decimal("50"), credit=Decimal("200"))
    assert LedgerService._signed_balance(NormalBalance.CREDIT, totals) == Decimal("150")


def test_pnl_totals_and_net_income(ledger: LedgerService):
    report = ledger.pnl(1, START, END)
    assert report.total_revenue == Decimal("1000")
    assert report.total_expenses == Decimal("300")
    assert report.net_income == Decimal("700")


def test_pnl_rolls_up_the_tree(ledger: LedgerService):
    report = ledger.pnl(1, START, END)

    # One revenue root (4000) that rolls 4110 up through 4100.
    assert len(report.revenue) == 1
    rev_root = report.revenue[0]
    assert rev_root.account_code == "4000"
    assert rev_root.balance == Decimal("1000")
    services = rev_root.children[0]
    assert services.account_code == "4100"
    assert services.balance == Decimal("1000")
    assert services.children[0].account_code == "4110"

    # Expenses root (5000) rolls two branches: 5320 (200) + 5810 (100) = 300.
    exp_root = report.expenses[0]
    assert exp_root.account_code == "5000"
    assert exp_root.balance == Decimal("300")
    branch_totals = {c.account_code: c.balance for c in exp_root.children}
    assert branch_totals == {"5300": Decimal("200"), "5800": Decimal("100")}


def test_pnl_report_to_dict_is_json_shaped(ledger: LedgerService):
    d = ledger.pnl(1, START, END).to_dict()
    assert d["status"] == "ok"
    assert d["net_income"] == 700.0
    assert d["period"] == {"start": "2026-01-01", "end": "2026-12-31"}
    assert isinstance(d["revenue"], list) and d["revenue"][0]["account_code"] == "4000"


def test_trial_balance_balances(ledger: LedgerService):
    tb = ledger.trial_balance(1, END)
    assert tb.is_balanced
    assert tb.total_debit == Decimal("1000")
    assert tb.total_credit == Decimal("1000")


def test_trial_balance_rows_use_normal_side(ledger: LedgerService):
    tb = ledger.trial_balance(1, END)
    rows = {r.account_code: r for r in tb.rows}
    # Cash: net-debit 700 sits in the debit column.
    assert rows["1110"].debit_balance == Decimal("700")
    assert rows["1110"].credit_balance == Decimal("0")
    # Revenue: credit-normal, shows in the credit column.
    assert rows["4110"].credit_balance == Decimal("1000")
    assert rows["4110"].debit_balance == Decimal("0")
    # Only posting leaves with activity appear (no parent/roll-up rows).
    assert all(code in {"1110", "4110", "5320", "5810"} for code in rows)


def test_balance_by_code_and_rollup(ledger: LedgerService):
    assert ledger.balance(1, "1110") == Decimal("700")   # leaf
    assert ledger.balance(1, "1000") == Decimal("700")   # asset root rolls up
    assert ledger.balance(1, "4000") == Decimal("1000")  # revenue root


def test_balance_by_id(ledger: LedgerService):
    assert ledger.balance(1, 22) == Decimal("200")  # 5320 Cloud Hosting


def test_unknown_account_raises(ledger: LedgerService):
    from app.application.accounting.errors import AccountNotFoundError

    with pytest.raises(AccountNotFoundError):
        ledger.balance(1, "9999")


def test_empty_ledger_is_balanced_and_zero():
    ledger = LedgerService(FakeLedgerRepository(accounts=sample_accounts(), totals={}))
    report = ledger.pnl(1, START, END)
    assert report.total_revenue == Decimal("0")
    assert report.net_income == Decimal("0")
    tb = ledger.trial_balance(1, END)
    assert tb.is_balanced and tb.rows == []
