"""Typed value objects that cross accounting-layer boundaries.

These are the DTOs the design standards call for: report results and journal-entry
drafts are dataclasses, never loose dicts, so callers get a stable, typed contract.
Report DTOs expose ``to_dict()`` for the chat layer to serialise to JSON without
reaching into internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.domain.enums import (
    AccountType,
    EscalationSource,
    JournalType,
    NormalBalance,
    TxnEventType,
)
from app.application.accounting.money import ZERO


# ── Posting drafts (input to persistence) ──────────────────────────────────
@dataclass(frozen=True)
class LineDraft:
    """A single validated debit/credit line, produced by :class:`JournalEntryBuilder`.

    Exactly one of ``debit_amount`` / ``credit_amount`` is non-zero; the account
    is guaranteed by the builder to be a posting leaf.
    """

    account_id: int
    account_code: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: Optional[str] = None
    reason_code: Optional[str] = None
    confidence_score: Optional[float] = None


@dataclass(frozen=True)
class JournalEntryDraft:
    """A balanced, leaves-only journal entry ready to persist as DRAFT or POSTED.

    Only :class:`JournalEntryBuilder` constructs these — its invariants (balanced,
    non-empty, posting leaves only) are the entry ticket. ``PostingService`` turns a
    draft into rows without re-checking money math.
    """

    business_id: int
    entry_date: date
    lines: List[LineDraft]
    description: Optional[str] = None
    event_type: TxnEventType = TxnEventType.MANUAL
    journal_type: JournalType = JournalType.GENERAL
    source: Optional[EscalationSource] = None
    confidence_score: Optional[float] = None
    source_document_id: Optional[int] = None

    @property
    def total_debit(self) -> Decimal:
        return sum((ln.debit_amount for ln in self.lines), ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((ln.credit_amount for ln in self.lines), ZERO)


# ── Report DTOs (output) ───────────────────────────────────────────────────
@dataclass
class AccountNode:
    """A node in the chart-of-accounts tree carrying its rolled-up balance.

    ``balance`` is signed in the account's normal-balance direction (a positive
    number means the account sits on its normal side). Leaf balances roll up into
    parents so the agent can render an indented report without doing arithmetic.
    """

    account_id: int
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: NormalBalance
    hierarchy_level: int
    posting_allowed: bool
    balance: Decimal
    children: List["AccountNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "account_type": self.account_type.value,
            "level": self.hierarchy_level,
            "balance": float(self.balance),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class PnLReport:
    """Cash-basis P&L: revenue and expense subtrees plus the net-income line."""

    business_id: int
    start: date
    end: date
    revenue: List[AccountNode]
    expenses: List[AccountNode]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal

    def to_dict(self) -> dict:
        return {
            "status": "ok",
            "business_id": self.business_id,
            "period": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "total_revenue": float(self.total_revenue),
            "total_expenses": float(self.total_expenses),
            "net_income": float(self.net_income),
            "revenue": [n.to_dict() for n in self.revenue],
            "expenses": [n.to_dict() for n in self.expenses],
        }


@dataclass(frozen=True)
class TrialBalanceRow:
    account_code: str
    account_name: str
    debit_balance: Decimal
    credit_balance: Decimal

    def to_dict(self) -> dict:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "debit": float(self.debit_balance),
            "credit": float(self.credit_balance),
        }


@dataclass
class TrialBalance:
    """Every posting account with its debit/credit balance; must foot (Σdr == Σcr)."""

    business_id: int
    as_of: date
    rows: List[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit

    def to_dict(self) -> dict:
        return {
            "business_id": self.business_id,
            "as_of": self.as_of.isoformat(),
            "total_debit": float(self.total_debit),
            "total_credit": float(self.total_credit),
            "is_balanced": self.is_balanced,
            "rows": [r.to_dict() for r in self.rows],
        }
