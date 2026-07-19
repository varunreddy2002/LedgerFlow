"""The posting invariants, enforced at construction time (Builder pattern).

A :class:`JournalEntryDraft` can only be produced by :class:`JournalEntryBuilder`,
and the builder refuses to hand one out unless:

* it has at least one line (:class:`EmptyJournalEntryError`);
* every referenced account is a posting leaf (:class:`PostingToNonLeafError`);
* Σ debits == Σ credits (:class:`UnbalancedEntryError`).

Callers never touch raw debit/credit signs: they say ``debit(account, amount)`` /
``credit(account, amount)``, or use :meth:`from_bank_movement`, which encodes the
owner-confirmed cash-basis rule (money-in ⇒ Dr cash / Cr revenue; money-out ⇒
Cr cash / Dr expense) and rejects a counter account whose type contradicts the
direction (:class:`DirectionConsistencyError`) so the ladder can escalate it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.logging import get_logger
from app.domain.enums import (
    AccountType,
    EscalationSource,
    JournalType,
    NormalBalance,
    TxnEventType,
)
from app.application.accounting.dtos import JournalEntryDraft, LineDraft
from app.application.accounting.errors import (
    AccountNotFoundError,
    DirectionConsistencyError,
    EmptyJournalEntryError,
    PostingToNonLeafError,
    UnbalancedEntryError,
)
from app.application.accounting.money import ZERO, to_money
from app.application.accounting.repository import AccountRecord

logger = get_logger(__name__)


class AccountCatalog:
    """An immutable lookup of a business's accounts, keyed by both id and code.

    Built from :class:`AccountRecord` snapshots so the builder never depends on the
    ORM or a live session. Construct via :meth:`from_records`.
    """

    def __init__(self, records: List[AccountRecord]) -> None:
        self._by_id: Dict[int, AccountRecord] = {r.id: r for r in records}
        self._by_code: Dict[str, AccountRecord] = {r.account_code: r for r in records}

    @classmethod
    def from_records(cls, records: List[AccountRecord]) -> "AccountCatalog":
        return cls(records)

    def get(self, ref) -> AccountRecord:
        """Resolve an account by integer id or string code, or raise."""
        record = self._by_id.get(ref) if isinstance(ref, int) else self._by_code.get(ref)
        if record is None:
            raise AccountNotFoundError(ref)
        return record


@dataclass
class _PendingLine:
    account: AccountRecord
    debit: Decimal
    credit: Decimal
    description: Optional[str]
    reason_code: Optional[str]
    confidence_score: Optional[float]


class JournalEntryBuilder:
    """Accumulates debit/credit lines and validates the double-entry invariants.

    Typical use::

        draft = (
            JournalEntryBuilder(catalog, business_id, entry_date, description="AWS")
            .debit("5320", "42.00", reason_code="rule:aws")
            .credit("1110", "42.00")
            .build()
        )
    """

    def __init__(
        self,
        catalog: AccountCatalog,
        business_id: int,
        entry_date: date,
        *,
        description: Optional[str] = None,
        event_type: TxnEventType = TxnEventType.MANUAL,
        journal_type: JournalType = JournalType.GENERAL,
        source: Optional[EscalationSource] = None,
        confidence_score: Optional[float] = None,
        source_document_id: Optional[int] = None,
    ) -> None:
        self._catalog = catalog
        self._business_id = business_id
        self._entry_date = entry_date
        self._description = description
        self._event_type = event_type
        self._journal_type = journal_type
        self._source = source
        self._confidence_score = confidence_score
        self._source_document_id = source_document_id
        self._lines: List[_PendingLine] = []

    # ── line accumulation (fluent) ──────────────────────────────────────────
    def debit(self, account_ref, amount, *, reason_code=None, description=None,
              confidence_score=None) -> "JournalEntryBuilder":
        """Add a debit line. Rejects non-leaf accounts immediately."""
        self._add(account_ref, debit=to_money(amount), credit=ZERO,
                  reason_code=reason_code, description=description,
                  confidence_score=confidence_score)
        return self

    def credit(self, account_ref, amount, *, reason_code=None, description=None,
               confidence_score=None) -> "JournalEntryBuilder":
        """Add a credit line. Rejects non-leaf accounts immediately."""
        self._add(account_ref, debit=ZERO, credit=to_money(amount),
                  reason_code=reason_code, description=description,
                  confidence_score=confidence_score)
        return self

    def _add(self, account_ref, *, debit, credit, reason_code, description,
             confidence_score) -> None:
        account = self._catalog.get(account_ref)
        if not account.posting_allowed:
            raise PostingToNonLeafError(account.account_code)
        self._lines.append(_PendingLine(
            account=account, debit=debit, credit=credit,
            description=description, reason_code=reason_code,
            confidence_score=confidence_score,
        ))

    # ── finalisation ────────────────────────────────────────────────────────
    def build(self) -> JournalEntryDraft:
        """Validate invariants and return an immutable draft, or raise."""
        if not self._lines:
            raise EmptyJournalEntryError()

        total_debit = sum((ln.debit for ln in self._lines), ZERO)
        total_credit = sum((ln.credit for ln in self._lines), ZERO)
        if total_debit != total_credit:
            raise UnbalancedEntryError(total_debit, total_credit)

        line_drafts = [
            LineDraft(
                account_id=ln.account.id,
                account_code=ln.account.account_code,
                debit_amount=ln.debit,
                credit_amount=ln.credit,
                description=ln.description,
                reason_code=ln.reason_code,
                confidence_score=ln.confidence_score,
            )
            for ln in self._lines
        ]
        logger.info(
            "[builder] built balanced draft business_id=%s lines=%d total=%s",
            self._business_id, len(line_drafts), total_debit,
        )
        return JournalEntryDraft(
            business_id=self._business_id,
            entry_date=self._entry_date,
            lines=line_drafts,
            description=self._description,
            event_type=self._event_type,
            journal_type=self._journal_type,
            source=self._source,
            confidence_score=self._confidence_score,
            source_document_id=self._source_document_id,
        )

    # ── cash-basis bank posting (owner-confirmed rules) ─────────────────────
    @classmethod
    def from_bank_movement(
        cls,
        catalog: AccountCatalog,
        *,
        business_id: int,
        entry_date: date,
        cash_account_ref,
        counter_account_ref,
        amount,
        cash_movement: NormalBalance,
        description: Optional[str] = None,
        reason_code: Optional[str] = None,
        source: Optional[EscalationSource] = None,
        confidence_score: Optional[float] = None,
        source_document_id: Optional[int] = None,
    ) -> JournalEntryDraft:
        """Build a balanced cash-basis entry for a bank row.

        The cash side is deterministic — money-in debits the cash asset, money-out
        credits it. The counter side is whatever the ladder classified, but its type
        must agree with the direction (cash-basis): money-in ⇒ counter is REVENUE,
        money-out ⇒ counter is EXPENSE. A contradiction raises
        :class:`DirectionConsistencyError` so the caller escalates to review instead
        of posting a nonsensical entry. Transfers / AR-AP settlements are *never*
        routed here — the pipeline escalates them upstream.
        """
        cash = catalog.get(cash_account_ref)
        counter = catalog.get(counter_account_ref)
        money = to_money(amount)

        if cash.account_type is not AccountType.ASSET:
            raise DirectionConsistencyError(
                f"Cash account {cash.account_code} is {cash.account_type.value}, "
                f"expected asset."
            )

        builder = cls(
            catalog, business_id, entry_date,
            description=description, event_type=TxnEventType.PAYMENT,
            journal_type=JournalType.BANK, source=source,
            confidence_score=confidence_score, source_document_id=source_document_id,
        )

        if cash_movement is NormalBalance.DEBIT:
            # Money IN — deposit. Dr Cash / Cr counter; counter must be revenue.
            if counter.account_type is not AccountType.REVENUE:
                raise DirectionConsistencyError(
                    f"Money-in must credit a REVENUE account, but "
                    f"{counter.account_code} is {counter.account_type.value}."
                )
            builder.debit(cash.account_code, money, description=description)
            builder.credit(counter.account_code, money, reason_code=reason_code,
                           description=description, confidence_score=confidence_score)
        else:
            # Money OUT — payment. Cr Cash / Dr counter; counter must be expense.
            if counter.account_type is not AccountType.EXPENSE:
                raise DirectionConsistencyError(
                    f"Money-out must debit an EXPENSE account, but "
                    f"{counter.account_code} is {counter.account_type.value}."
                )
            builder.debit(counter.account_code, money, reason_code=reason_code,
                          description=description, confidence_score=confidence_score)
            builder.credit(cash.account_code, money, description=description)

        return builder.build()
