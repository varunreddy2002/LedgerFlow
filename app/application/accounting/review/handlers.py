"""Per-item-type resolution behaviour (Strategy) + the dispatch registry.

Each :class:`ReviewItemHandler` knows how to resolve one *kind* of review item. A
:class:`ReviewItemHandlerRegistry` maps :class:`ReviewItemType` → handler so
``ReviewQueueService`` dispatches by data, never an ``if/elif`` ladder — adding a new
gap type later is a one-line registration (Open/Closed).

Tonight ``uncategorized`` and ``large_amount`` are fully implemented by the shared
:class:`BankRowReviewHandler` (both resolve a bank row into a posted entry); every
other type is registered to :class:`StubReviewHandler`, which refuses loudly so the
mechanism is generic and the gaps are explicit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import ApprovalDecision, EscalationSource, ReviewItemType, ReviewStatus
from app.domain.models.ledger import ApprovalEvent, ReviewItem
from app.application.accounting.errors import (
    DirectionConsistencyError,
    ReviewError,
    UnsupportedReviewItemTypeError,
)
from app.application.accounting.journal_entry_builder import AccountCatalog, JournalEntryBuilder
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import BankTransactionRepository
from app.application.accounting.review.dtos import ResolutionResult, ReviewResolution
from app.application.accounting.review.rule_learning import RuleLearner

logger = get_logger(__name__)

_DISMISS_DECISIONS = {ApprovalDecision.REJECTED}


class ReviewItemHandler(ABC):
    """Strategy interface: resolve one review item into a ledger action."""

    @abstractmethod
    def resolve(self, item: ReviewItem, resolution: ReviewResolution) -> ResolutionResult:
        ...


class BankRowReviewHandler(ReviewItemHandler):
    """Resolves a review item whose subject is a bank row (uncategorized / large_amount).

    On approve/modify: build a balanced cash-basis entry to the chosen account, post
    it, mark the bank row posted, and (optionally) learn a rule. On reject: dismiss
    the item and exclude the bank row. Amounts always come from the bank row — the
    human only chooses the account.
    """

    def __init__(
        self,
        session: Session,
        business_id: int,
        catalog: AccountCatalog,
        posting: PostingService,
        bank_repo: BankTransactionRepository,
        rule_learner: RuleLearner,
    ) -> None:
        self._session = session
        self._business_id = business_id
        self._catalog = catalog
        self._posting = posting
        self._bank_repo = bank_repo
        self._rule_learner = rule_learner

    def resolve(self, item: ReviewItem, resolution: ReviewResolution) -> ResolutionResult:
        txn = self._bank_repo.get(item.subject_id)
        if txn is None:
            raise ReviewError(
                f"Bank transaction {item.subject_id} for review item {item.id} not found."
            )

        if resolution.decision in _DISMISS_DECISIONS:
            return self._dismiss(item, txn, resolution)

        account_code = resolution.account_code or (item.proposed_resolution or {}).get("account_code")
        if not account_code:
            raise ReviewError(
                f"Review item {item.id} has no proposed account and none was supplied; "
                f"cannot post."
            )

        try:
            draft = JournalEntryBuilder.from_bank_movement(
                self._catalog,
                business_id=self._business_id,
                entry_date=txn.transaction_date,
                cash_account_ref=txn.gl_account_id,
                counter_account_ref=account_code,
                amount=txn.amount,
                cash_movement=txn.cash_movement,
                description=txn.description,
                reason_code=f"review:{item.id}",
                source=EscalationSource.AGENT,
                confidence_score=item.confidence,
            )
        except DirectionConsistencyError as exc:
            # The human picked an account whose type contradicts the cash direction.
            raise ReviewError(str(exc)) from exc

        entry = self._posting.post(
            draft, decided_by=resolution.actor, decision=resolution.decision,
            notes=resolution.notes or f"resolved review item {item.id}",
        )
        self._bank_repo.mark_posted(txn, entry.id)
        self._finalize(item, resolution, ReviewStatus.RESOLVED)

        rule_created = False
        if resolution.create_rule:
            rule_created = self._rule_learner.learn(txn.description, account_code)

        logger.info(
            "[review] resolved item=%s type=%s -> je=%s account=%s rule_created=%s",
            item.id, item.item_type.value, entry.id, account_code, rule_created,
        )
        return ResolutionResult(
            review_item_id=item.id,
            status="resolved",
            journal_entry_id=entry.id,
            account_code=account_code,
            rule_created=rule_created,
            message=f"Posted to {account_code}." + (" Learned a rule." if rule_created else ""),
        )

    def _dismiss(self, item, txn, resolution) -> ResolutionResult:
        from app.domain.enums import BankTxnStatus

        txn.status = BankTxnStatus.EXCLUDED
        self._finalize(item, resolution, ReviewStatus.DISMISSED)
        logger.info("[review] dismissed item=%s (bank row excluded)", item.id)
        return ResolutionResult(
            review_item_id=item.id,
            status="dismissed",
            message="Review item dismissed; bank row excluded.",
        )

    def _finalize(self, item, resolution, status: ReviewStatus) -> None:
        item.status = status
        item.decision = resolution.decision
        item.decided_by = resolution.actor
        item.decided_at = datetime.utcnow()
        item.resolution_notes = resolution.notes
        self._session.add(ApprovalEvent(
            review_item_id=item.id,
            decision=resolution.decision,
            decision_notes=resolution.notes,
            decided_by=resolution.actor,
        ))
        self._session.flush()


class StubReviewHandler(ReviewItemHandler):
    """Placeholder for item types not yet implemented — refuses loudly.

    Keeps the queue *generic*: the type is registered and listable, but resolving it
    raises so nothing silently half-works. Swap in a real handler to enable it.
    """

    def __init__(self, item_type: ReviewItemType) -> None:
        self._item_type = item_type

    def resolve(self, item: ReviewItem, resolution: ReviewResolution) -> ResolutionResult:
        raise UnsupportedReviewItemTypeError(self._item_type.value)


class ReviewItemHandlerRegistry:
    """Maps a review-item type to its handler (data-driven dispatch)."""

    def __init__(self) -> None:
        self._handlers: Dict[ReviewItemType, ReviewItemHandler] = {}

    def register(self, item_type: ReviewItemType, handler: ReviewItemHandler) -> None:
        self._handlers[item_type] = handler

    def get(self, item_type: ReviewItemType) -> ReviewItemHandler:
        handler = self._handlers.get(item_type)
        if handler is None:
            raise UnsupportedReviewItemTypeError(item_type.value)
        return handler


def build_registry(bank_row_handler: BankRowReviewHandler) -> ReviewItemHandlerRegistry:
    """Register the two fully-implemented types + stubs for the rest.

    ``uncategorized`` and ``large_amount`` → the shared bank-row handler; every other
    :class:`ReviewItemType` → a :class:`StubReviewHandler` (generic but explicit).
    """
    registry = ReviewItemHandlerRegistry()
    registry.register(ReviewItemType.UNCATEGORIZED, bank_row_handler)
    registry.register(ReviewItemType.LARGE_AMOUNT, bank_row_handler)
    for item_type in ReviewItemType:
        if item_type not in (ReviewItemType.UNCATEGORIZED, ReviewItemType.LARGE_AMOUNT):
            registry.register(item_type, StubReviewHandler(item_type))
    return registry
