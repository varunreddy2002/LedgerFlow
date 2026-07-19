"""Data-access abstraction for the ledger (Repository pattern).

`LedgerService` and the report tools depend on the :class:`LedgerRepository`
*protocol*, not on SQLAlchemy — that is the DIP seam the standards require. The
concrete :class:`SqlAlchemyLedgerRepository` is the only place that knows about the
ORM; unit tests substitute an in-memory fake implementing the same protocol.

The repository deliberately returns *primitive records and aggregates*, never ORM
objects, so all sign/rollup arithmetic lives in the pure service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import (
    AccountType,
    BankTxnStatus,
    JournalEntryStatus,
    NormalBalance,
    ReviewItemType,
    ReviewStatus,
)
from app.domain.models.ledger import (
    Account,
    BankTransaction,
    JournalEntry,
    JournalEntryLine,
    ReviewItem,
)
from app.application.accounting.money import ZERO


@dataclass(frozen=True)
class AccountRecord:
    """A flat snapshot of one chart-of-accounts row (no ORM identity)."""

    id: int
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: NormalBalance
    hierarchy_level: int
    posting_allowed: bool
    parent_account_id: Optional[int]
    is_active: bool


@dataclass(frozen=True)
class LineTotals:
    """Summed debit/credit postings for a single account."""

    debit: Decimal
    credit: Decimal


class LedgerRepository(Protocol):
    """Read side the ledger service depends on. Reads only POSTED entries for
    balance aggregates — draft/pending entries never affect the books."""

    def list_accounts(self, business_id: int) -> List[AccountRecord]:
        """All accounts for a business, ordered by code."""
        ...

    def posted_line_totals(
        self,
        business_id: int,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Dict[int, LineTotals]:
        """Sum debit/credit per account over POSTED entries whose ``entry_date``
        falls within the inclusive ``[start, end]`` window (either bound optional)."""
        ...


class SqlAlchemyLedgerRepository:
    """SQLAlchemy-backed :class:`LedgerRepository`. One instance wraps one Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_accounts(self, business_id: int) -> List[AccountRecord]:
        rows = (
            self._session.execute(
                select(Account)
                .where(Account.business_id == business_id)
                .order_by(Account.account_code)
            )
            .scalars()
            .all()
        )
        return [
            AccountRecord(
                id=a.id,
                account_code=a.account_code,
                account_name=a.account_name,
                account_type=a.account_type,
                normal_balance=a.normal_balance,
                hierarchy_level=a.hierarchy_level,
                posting_allowed=a.posting_allowed,
                parent_account_id=a.parent_account_id,
                is_active=a.is_active,
            )
            for a in rows
        ]

    def posted_line_totals(
        self,
        business_id: int,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Dict[int, LineTotals]:
        stmt = (
            select(
                JournalEntryLine.account_id,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.business_id == business_id,
                JournalEntry.status == JournalEntryStatus.POSTED,
            )
            .group_by(JournalEntryLine.account_id)
        )
        if start is not None:
            stmt = stmt.where(JournalEntry.entry_date >= start)
        if end is not None:
            stmt = stmt.where(JournalEntry.entry_date <= end)

        totals: Dict[int, LineTotals] = {}
        for account_id, debit, credit in self._session.execute(stmt).all():
            totals[account_id] = LineTotals(
                debit=Decimal(debit or 0), credit=Decimal(credit or 0)
            )
        return totals


class BankTransactionRepository:
    """Data access for raw bank rows (the ladder's source). Wraps one Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, bank_transaction_id: int) -> Optional[BankTransaction]:
        return self._session.get(BankTransaction, bank_transaction_id)

    def list_by_status(
        self, business_id: int, status: BankTxnStatus
    ) -> List[BankTransaction]:
        return (
            self._session.query(BankTransaction)
            .filter(
                BankTransaction.business_id == business_id,
                BankTransaction.status == status,
            )
            .order_by(BankTransaction.transaction_date, BankTransaction.id)
            .all()
        )

    def mark_posted(self, txn: BankTransaction, journal_entry_id: int) -> None:
        txn.status = BankTxnStatus.POSTED
        txn.journal_entry_id = journal_entry_id
        self._session.flush()

    def mark_proposed(self, txn: BankTransaction) -> None:
        txn.status = BankTxnStatus.PROPOSED
        self._session.flush()


class ReviewItemRepository:
    """Data access for the unified review/exception queue. Wraps one Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, review_item_id: int) -> Optional[ReviewItem]:
        return self._session.get(ReviewItem, review_item_id)

    def add(self, item: ReviewItem) -> ReviewItem:
        self._session.add(item)
        self._session.flush()
        return item

    def list(
        self,
        business_id: int,
        status: Optional[ReviewStatus] = None,
        item_type: Optional[ReviewItemType] = None,
    ) -> List[ReviewItem]:
        query = self._session.query(ReviewItem).filter(
            ReviewItem.business_id == business_id
        )
        if status is not None:
            query = query.filter(ReviewItem.status == status)
        if item_type is not None:
            query = query.filter(ReviewItem.item_type == item_type)
        return query.order_by(ReviewItem.id).all()
