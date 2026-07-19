"""ReviewQueueService — orchestrates the unified exception queue (Service layer).

Lists open review items and resolves them by dispatching to a per-type handler
(Strategy). Resolution posts the journal entry via :class:`PostingService` and,
optionally, grows the deterministic layer via :class:`RuleLearner`. The service owns
orchestration only — persistence lives in repositories, ledger math in the builder.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import ReviewItemType, ReviewStatus
from app.domain.models.ledger import BankTransaction
from app.application.accounting.errors import (
    ReviewItemAlreadyResolvedError,
    ReviewItemNotFoundError,
)
from app.application.accounting.journal_entry_builder import AccountCatalog, JournalEntryBuilder
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import (
    BankTransactionRepository,
    ReviewItemRepository,
    SqlAlchemyLedgerRepository,
)
from app.application.accounting.review.dtos import (
    ResolutionResult,
    ReviewItemView,
    ReviewResolution,
)
from app.application.accounting.review.handlers import (
    BankRowReviewHandler,
    ReviewItemHandlerRegistry,
    build_registry,
)
from app.application.accounting.review.rule_learning import RuleLearner

logger = get_logger(__name__)


class ReviewQueueService:
    """Lists and resolves review items for one business."""

    def __init__(
        self,
        session: Session,
        business_id: int,
        review_repo: ReviewItemRepository,
        bank_repo: BankTransactionRepository,
        registry: ReviewItemHandlerRegistry,
        catalog: AccountCatalog,
    ) -> None:
        self._session = session
        self._business_id = business_id
        self._review_repo = review_repo
        self._bank_repo = bank_repo
        self._registry = registry
        self._catalog = catalog

    # ── read ─────────────────────────────────────────────────────────────────
    def list(
        self,
        status: Optional[ReviewStatus] = ReviewStatus.OPEN,
        item_type: Optional[ReviewItemType] = None,
    ) -> List[ReviewItemView]:
        """List review items (default: open), enriched with the bank row's text."""
        items = self._review_repo.list(self._business_id, status=status, item_type=item_type)
        views: List[ReviewItemView] = []
        for item in items:
            description = amount = None
            if item.subject_type == "bank_transaction":
                txn = self._bank_repo.get(item.subject_id)
                if txn is not None:
                    description = txn.description
                    amount = str(txn.amount)
            views.append(ReviewItemView.from_model(item, description=description, amount=amount))
        return views

    def preview(self, item_id: int, resolution: ReviewResolution) -> dict:
        """Return a read-only preview of the entry that resolving would post.

        Never writes. Used by the chat approval interrupt so the owner sees the exact
        Dr/Cr lines before confirming. Returns ``{"error": ...}`` if the choice is
        invalid (e.g. an account whose type contradicts the cash direction).
        """
        from app.domain.enums import ApprovalDecision

        item = self._review_repo.get(item_id)
        if item is None or item.business_id != self._business_id:
            raise ReviewItemNotFoundError(item_id)

        base = {
            "review_item_id": item.id,
            "item_type": item.item_type.value,
            "decision": resolution.decision.value,
        }
        if item.subject_type != "bank_transaction":
            base["error"] = f"Preview not supported for subject {item.subject_type!r}."
            return base

        txn = self._bank_repo.get(item.subject_id)
        if txn is None:
            base["error"] = f"Bank transaction {item.subject_id} not found."
            return base
        base.update({"description": txn.description, "amount": str(txn.amount)})

        if resolution.decision is ApprovalDecision.REJECTED:
            base["action"] = "dismiss"
            return base

        account_code = resolution.account_code or (item.proposed_resolution or {}).get("account_code")
        if not account_code:
            base["error"] = "No account proposed and none supplied."
            return base
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
            )
        except Exception as exc:  # DirectionConsistencyError / AccountNotFoundError
            base["error"] = str(exc)
            return base

        base["action"] = "post"
        base["account_code"] = account_code
        base["lines"] = [
            {
                "account_code": ln.account_code,
                "debit": str(ln.debit_amount),
                "credit": str(ln.credit_amount),
            }
            for ln in draft.lines
        ]
        return base

    # ── write ────────────────────────────────────────────────────────────────
    def resolve(self, item_id: int, resolution: ReviewResolution) -> ResolutionResult:
        """Resolve one open review item, dispatching to its type handler.

        Raises :class:`ReviewItemNotFoundError` / :class:`ReviewItemAlreadyResolvedError`
        for bad requests. On success the entry is POSTED and the item is RESOLVED.
        """
        item = self._review_repo.get(item_id)
        if item is None or item.business_id != self._business_id:
            raise ReviewItemNotFoundError(item_id)
        if item.status is not ReviewStatus.OPEN:
            raise ReviewItemAlreadyResolvedError(item_id)

        handler = self._registry.get(item.item_type)
        logger.info(
            "[review_queue] resolving item=%s type=%s decision=%s by=%s",
            item_id, item.item_type.value, resolution.decision.value, resolution.actor,
        )
        return handler.resolve(item, resolution)


def build_review_service(session: Session, business_id: int) -> ReviewQueueService:
    """Assemble a :class:`ReviewQueueService` with all dependencies bound to a session."""
    ledger_repo = SqlAlchemyLedgerRepository(session)
    catalog = AccountCatalog.from_records(ledger_repo.list_accounts(business_id))
    review_repo = ReviewItemRepository(session)
    bank_repo = BankTransactionRepository(session)
    posting = PostingService(session)
    rule_learner = RuleLearner(session, business_id)

    bank_row_handler = BankRowReviewHandler(
        session, business_id, catalog, posting, bank_repo, rule_learner
    )
    registry = build_registry(bank_row_handler)
    return ReviewQueueService(session, business_id, review_repo, bank_repo, registry, catalog)
