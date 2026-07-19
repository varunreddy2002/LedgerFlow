"""In-memory test doubles for the accounting core.

These let the deterministic layers (ledger, builder) be unit-tested with **no
database** — the whole point of depending on the :class:`LedgerRepository`
protocol. A tiny but structurally complete 3-level COA is defined here and reused
across tests.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.domain.enums import AccountType, NormalBalance
from app.application.accounting.money import ZERO
from app.application.accounting.repository import AccountRecord, LineTotals

_BUSINESS_ID = 1

# (id, code, name, type, normal_balance, level, posting_allowed, parent_id)
_COA = [
    (1, "1000", "Assets", AccountType.ASSET, NormalBalance.DEBIT, 1, False, None),
    (2, "1100", "Cash", AccountType.ASSET, NormalBalance.DEBIT, 2, False, 1),
    (3, "1110", "Operating Checking", AccountType.ASSET, NormalBalance.DEBIT, 3, True, 2),
    (10, "4000", "Revenue", AccountType.REVENUE, NormalBalance.CREDIT, 1, False, None),
    (11, "4100", "Services", AccountType.REVENUE, NormalBalance.CREDIT, 2, False, 10),
    (12, "4110", "Consulting Revenue", AccountType.REVENUE, NormalBalance.CREDIT, 3, True, 11),
    (20, "5000", "Expenses", AccountType.EXPENSE, NormalBalance.DEBIT, 1, False, None),
    (21, "5300", "Technology", AccountType.EXPENSE, NormalBalance.DEBIT, 2, False, 20),
    (22, "5320", "Cloud Hosting", AccountType.EXPENSE, NormalBalance.DEBIT, 3, True, 21),
    (23, "5800", "Financial", AccountType.EXPENSE, NormalBalance.DEBIT, 2, False, 20),
    (24, "5810", "Bank Fees", AccountType.EXPENSE, NormalBalance.DEBIT, 3, True, 23),
]


def sample_accounts() -> List[AccountRecord]:
    """A structurally complete 3-level consulting COA (assets/revenue/expenses)."""
    return [
        AccountRecord(
            id=i, account_code=code, account_name=name, account_type=atype,
            normal_balance=nb, hierarchy_level=level, posting_allowed=posting,
            parent_account_id=parent, is_active=True,
        )
        for (i, code, name, atype, nb, level, posting, parent) in _COA
    ]


def _d(x) -> Decimal:
    return Decimal(str(x))


def sample_totals() -> Dict[int, LineTotals]:
    """Posted aggregates for three coherent, balanced entries:

    * Dr Cash 1000 / Cr Consulting Revenue 1000  (a customer deposit)
    * Dr Cloud Hosting 200 / Cr Cash 200         (an AWS payment)
    * Dr Bank Fees 100 / Cr Cash 100             (a wire fee)

    → Cash net-debit 700, Revenue 1000, Hosting 200, Bank Fees 100. Σdr == Σcr.
    """
    return {
        3: LineTotals(debit=_d(1000), credit=_d(300)),   # 1110 Operating Checking
        12: LineTotals(debit=ZERO, credit=_d(1000)),     # 4110 Consulting Revenue
        22: LineTotals(debit=_d(200), credit=ZERO),      # 5320 Cloud Hosting
        24: LineTotals(debit=_d(100), credit=ZERO),      # 5810 Bank Fees
    }


class FakeLedgerRepository:
    """In-memory :class:`LedgerRepository`. Date bounds are accepted but ignored —
    tests exercise the sign/rollup math, not SQL date filtering."""

    def __init__(
        self,
        accounts: Optional[List[AccountRecord]] = None,
        totals: Optional[Dict[int, LineTotals]] = None,
    ) -> None:
        self._accounts = accounts if accounts is not None else sample_accounts()
        self._totals = totals if totals is not None else sample_totals()

    def list_accounts(self, business_id: int) -> List[AccountRecord]:
        return list(self._accounts)

    def posted_line_totals(
        self, business_id: int, start: Optional[date] = None, end: Optional[date] = None
    ) -> Dict[int, LineTotals]:
        return dict(self._totals)


# ── Fakes for the escalation ladder (no DB) ─────────────────────────────────
class _PostedEntry:
    def __init__(self, entry_id: int) -> None:
        self.id = entry_id


class FakePostingService:
    """Captures posted drafts instead of writing to a database."""

    def __init__(self) -> None:
        self.posted: List = []
        self._seq = 1000

    def post(self, draft, *, decided_by="system", decision=None, notes=None) -> _PostedEntry:
        self._seq += 1
        entry = _PostedEntry(self._seq)
        self.posted.append(
            {"id": entry.id, "draft": draft, "decided_by": decided_by, "decision": decision}
        )
        return entry


class FakeBankTxn:
    """A minimal stand-in for the BankTransaction ORM row used by handlers."""

    def __init__(self, txn_id: int) -> None:
        self.id = txn_id
        self.status = None
        self.journal_entry_id = None


class FakeBankRepo:
    def __init__(self, txns: Optional[List[FakeBankTxn]] = None) -> None:
        self._txns = {t.id: t for t in (txns or [])}
        self.posted: List = []
        self.proposed: List = []

    def register(self, txn: FakeBankTxn) -> FakeBankTxn:
        self._txns[txn.id] = txn
        return txn

    def get(self, txn_id: int) -> Optional[FakeBankTxn]:
        return self._txns.get(txn_id)

    def mark_posted(self, txn: FakeBankTxn, journal_entry_id: int) -> None:
        txn.status = "posted"
        txn.journal_entry_id = journal_entry_id
        self.posted.append((txn.id, journal_entry_id))

    def mark_proposed(self, txn: FakeBankTxn) -> None:
        txn.status = "proposed"
        self.proposed.append(txn.id)


class FakeReviewRepo:
    def __init__(self) -> None:
        self.items: List = []
        self._seq = 0

    def add(self, item):
        self._seq += 1
        item.id = self._seq
        self.items.append(item)
        return item

