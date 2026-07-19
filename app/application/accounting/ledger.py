"""The ledger — trusted, deterministic accounting primitives.

This module is the single source of accounting truth. The debit/credit sign
convention lives here *once* and nowhere else: every report derives from
:meth:`LedgerService._signed_balance`. There are no LLM calls here — the agent may
present these numbers but never computes them.

Design:

* :class:`LedgerService` depends on the :class:`LedgerRepository` protocol (DIP),
  so it is unit-tested against an in-memory fake with zero database.
* Balances read **only** POSTED entries; drafts and pending approvals are invisible
  to reports by construction.
* Reports return typed DTOs (:mod:`app.application.accounting.dtos`) that carry the
  COA hierarchy, so callers render rolled-up, indented statements without arithmetic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Union

from app.core.logging import get_logger
from app.domain.enums import AccountType, NormalBalance
from app.application.accounting.dtos import (
    AccountNode,
    PnLReport,
    TrialBalance,
    TrialBalanceRow,
)
from app.application.accounting.errors import AccountNotFoundError
from app.application.accounting.money import ZERO
from app.application.accounting.repository import (
    AccountRecord,
    LedgerRepository,
    LineTotals,
)

logger = get_logger(__name__)

AccountRef = Union[int, str]


class LedgerService:
    """Computes balances and financial statements from POSTED journal entries.

    All methods are read-only and side-effect free. Construct one per unit of work,
    passing a repository bound to the active session.
    """

    def __init__(self, repository: LedgerRepository) -> None:
        self._repo = repository

    # ── sign convention (the one place it lives) ───────────────────────────
    @staticmethod
    def _signed_balance(normal_balance: NormalBalance, totals: LineTotals) -> Decimal:
        """Return an account's balance signed in its normal-balance direction.

        A debit-normal account (asset/expense) increases with debits; a
        credit-normal account (liability/equity/revenue) increases with credits.
        A positive result means the account sits on its normal side.
        """
        if normal_balance is NormalBalance.DEBIT:
            return totals.debit - totals.credit
        return totals.credit - totals.debit

    # ── tree construction with rolled-up balances ──────────────────────────
    def _build_forest(
        self, accounts: List[AccountRecord], totals: Dict[int, LineTotals]
    ) -> tuple[List[AccountNode], Dict[int, AccountNode]]:
        """Build the COA forest, rolling leaf balances up into their ancestors.

        Returns the level-1 root nodes and an id→node index. Because the COA keeps
        every descendant of a type header within the same ``account_type``, summing
        a child's normal-signed balance into its parent is always consistent.
        """
        nodes: Dict[int, AccountNode] = {
            a.id: AccountNode(
                account_id=a.id,
                account_code=a.account_code,
                account_name=a.account_name,
                account_type=a.account_type,
                normal_balance=a.normal_balance,
                hierarchy_level=a.hierarchy_level,
                posting_allowed=a.posting_allowed,
                balance=self._signed_balance(a.normal_balance, totals.get(a.id, _EMPTY)),
            )
            for a in accounts
        }

        roots: List[AccountNode] = []
        by_id = {a.id: a for a in accounts}
        # Link children to parents.
        for a in accounts:
            node = nodes[a.id]
            parent_id = a.parent_account_id
            if parent_id is not None and parent_id in nodes:
                nodes[parent_id].children.append(node)
            else:
                roots.append(node)

        # Roll leaf balances upward (deepest level first so parents see final children).
        for a in sorted(accounts, key=lambda x: x.hierarchy_level, reverse=True):
            node = nodes[a.id]
            parent_id = by_id[a.id].parent_account_id
            if parent_id is not None and parent_id in nodes:
                nodes[parent_id].balance += node.balance

        # Deterministic ordering for presentation.
        for node in nodes.values():
            node.children.sort(key=lambda n: n.account_code)
        roots.sort(key=lambda n: n.account_code)
        return roots, nodes

    # ── public primitives ──────────────────────────────────────────────────
    def balance(
        self, business_id: int, account: AccountRef, as_of: Optional[date] = None
    ) -> Decimal:
        """Signed balance of one account (by id or code) in its normal direction.

        For a non-leaf account the balance is the rolled-up total of its subtree.
        """
        accounts = self._repo.list_accounts(business_id)
        target = self._resolve(accounts, account)
        totals = self._repo.posted_line_totals(business_id, end=as_of)
        _, index = self._build_forest(accounts, totals)
        return index[target.id].balance

    def account_tree(
        self, business_id: int, as_of: Optional[date] = None
    ) -> List[AccountNode]:
        """The full chart of accounts as a forest of level-1 roots, each carrying
        its rolled-up balance as of ``as_of`` (or all-time if omitted)."""
        accounts = self._repo.list_accounts(business_id)
        totals = self._repo.posted_line_totals(business_id, end=as_of)
        roots, _ = self._build_forest(accounts, totals)
        return roots

    def pnl(self, business_id: int, start: date, end: date) -> PnLReport:
        """Cash-basis P&L over ``[start, end]``.

        Revenue and expense subtrees carry rolled-up balances; ``net_income`` is
        ``total_revenue - total_expenses``. This is the official number.
        """
        accounts = self._repo.list_accounts(business_id)
        totals = self._repo.posted_line_totals(business_id, start=start, end=end)
        roots, _ = self._build_forest(accounts, totals)

        revenue = [n for n in roots if n.account_type is AccountType.REVENUE]
        expenses = [n for n in roots if n.account_type is AccountType.EXPENSE]
        total_revenue = sum((n.balance for n in revenue), ZERO)
        total_expenses = sum((n.balance for n in expenses), ZERO)
        net_income = total_revenue - total_expenses

        logger.info(
            "[ledger.pnl] business_id=%s %s..%s revenue=%s expenses=%s net=%s",
            business_id, start, end, total_revenue, total_expenses, net_income,
        )
        return PnLReport(
            business_id=business_id,
            start=start,
            end=end,
            revenue=revenue,
            expenses=expenses,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=net_income,
        )

    def trial_balance(self, business_id: int, as_of: date) -> TrialBalance:
        """Every posting account with a balance, split into debit/credit columns.

        Asserts the books balance (Σ debit column == Σ credit column). Because every
        POSTED entry is itself balanced, this equality is a structural guarantee; the
        check catches any corruption that slipped past the posting invariants.
        """
        accounts = self._repo.list_accounts(business_id)
        totals = self._repo.posted_line_totals(business_id, end=as_of)

        rows: List[TrialBalanceRow] = []
        total_debit = ZERO
        total_credit = ZERO
        for a in accounts:
            if not a.posting_allowed:
                continue
            t = totals.get(a.id)
            if t is None:
                continue
            net_debit = t.debit - t.credit  # raw, direction-agnostic
            if net_debit == ZERO:
                continue
            if net_debit > ZERO:
                debit_balance, credit_balance = net_debit, ZERO
            else:
                debit_balance, credit_balance = ZERO, -net_debit
            total_debit += debit_balance
            total_credit += credit_balance
            rows.append(
                TrialBalanceRow(
                    account_code=a.account_code,
                    account_name=a.account_name,
                    debit_balance=debit_balance,
                    credit_balance=credit_balance,
                )
            )

        rows.sort(key=lambda r: r.account_code)
        report = TrialBalance(
            business_id=business_id,
            as_of=as_of,
            rows=rows,
            total_debit=total_debit,
            total_credit=total_credit,
        )
        if not report.is_balanced:
            # This should be impossible if posting invariants held; surface loudly.
            logger.error(
                "[ledger.trial_balance] OUT OF BALANCE business_id=%s sum_debit=%s sum_credit=%s",
                business_id, total_debit, total_credit,
            )
        else:
            logger.info(
                "[ledger.trial_balance] business_id=%s balanced at %s (total=%s)",
                business_id, as_of, total_debit,
            )
        return report

    # ── helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def _resolve(accounts: List[AccountRecord], ref: AccountRef) -> AccountRecord:
        for a in accounts:
            if (isinstance(ref, int) and a.id == ref) or (
                isinstance(ref, str) and a.account_code == ref
            ):
                return a
        raise AccountNotFoundError(ref)


_EMPTY = LineTotals(debit=ZERO, credit=ZERO)
