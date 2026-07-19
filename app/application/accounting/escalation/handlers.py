"""The escalation ladder handlers (Chain of Responsibility).

Each handler either *resolves* a bank row (terminal) or *forwards* it to the next
handler, optionally enriching the shared :class:`LadderContext`:

* :class:`RuleHandler`   — deterministic rules first. A high-confidence match under
  the large-amount threshold auto-posts a balanced entry; a low-confidence match, a
  large amount, or a direction contradiction forwards (with the proposal attached).
* :class:`AgentHandler`  — only runs when no rule matched; asks the (LLM) classifier
  to *choose an account*. Never posts, never computes amounts — always forwards.
* :class:`ReviewHandler` — the tail. Always resolves by creating a review item, so
  the chain can never fall through.

The bright line the design demands: the money math (amounts, balancing) is the
builder's; the agent only picks *which* account. Nothing here posts without either a
high-confidence deterministic rule or (later) a human approval on the review item.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.logging import get_logger
from app.domain.enums import ApprovalDecision, EscalationSource, ReviewItemType, ReviewStatus
from app.domain.models.ledger import ReviewItem
from app.application.accounting.errors import DirectionConsistencyError, EscalationError
from app.application.accounting.journal_entry_builder import AccountCatalog, JournalEntryBuilder
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import (
    AccountRecord,
    BankTransactionRepository,
    ReviewItemRepository,
)
from app.application.accounting.rule_engine import AccountingRuleEngine
from app.application.accounting.escalation.context import (
    AccountClassifier,
    AccountProposal,
    LadderContext,
    LadderOutcome,
)

logger = get_logger(__name__)

SUBJECT_BANK_TRANSACTION = "bank_transaction"


class EscalationHandler(ABC):
    """Base link in the chain. Subclasses implement :meth:`handle`."""

    def __init__(self) -> None:
        self._next: Optional[EscalationHandler] = None

    def set_next(self, handler: "EscalationHandler") -> "EscalationHandler":
        """Set the successor and return it (so links can be chained fluently)."""
        self._next = handler
        return handler

    @abstractmethod
    def handle(self, ctx: LadderContext) -> LadderOutcome:
        ...

    def _forward(self, ctx: LadderContext) -> LadderOutcome:
        if self._next is None:
            raise EscalationError(
                "Escalation ladder fell through with no terminal handler "
                f"(bank_transaction_id={ctx.bank_transaction_id})."
            )
        return self._next.handle(ctx)


class RuleHandler(EscalationHandler):
    """Deterministic layer: match ``accounting_rules``, apply the confidence gate and
    the large-amount override, and auto-post high-confidence small matches."""

    def __init__(
        self,
        rule_engine: AccountingRuleEngine,
        catalog: AccountCatalog,
        posting_service: PostingService,
        bank_repo: BankTransactionRepository,
        *,
        confidence_threshold: float,
        large_amount_threshold: float,
    ) -> None:
        super().__init__()
        self._rules = rule_engine
        self._catalog = catalog
        self._posting = posting_service
        self._bank_repo = bank_repo
        self._confidence_threshold = confidence_threshold
        self._large_amount_threshold = large_amount_threshold

    def handle(self, ctx: LadderContext) -> LadderOutcome:
        match = self._rules.match(ctx.fields)
        if match is None:
            logger.info("[ladder.rule] no rule matched bank_txn=%s -> escalate",
                        ctx.bank_transaction_id)
            return self._forward(ctx)

        ctx.proposal = AccountProposal(
            account_code=match.account_code,
            confidence=match.confidence,
            source=EscalationSource.RULE,
            reason_code=match.reason_code,
        )

        if match.confidence < self._confidence_threshold:
            logger.info(
                "[ladder.rule] bank_txn=%s matched but conf %.2f < gate %.2f -> review",
                ctx.bank_transaction_id, match.confidence, self._confidence_threshold,
            )
            return self._forward(ctx)

        if float(ctx.amount) > self._large_amount_threshold:
            ctx.large_amount = True
            logger.info(
                "[ladder.rule] bank_txn=%s amount %s over large threshold %.2f -> review",
                ctx.bank_transaction_id, ctx.amount, self._large_amount_threshold,
            )
            return self._forward(ctx)

        # High confidence, small amount → auto-post a balanced entry.
        try:
            draft = JournalEntryBuilder.from_bank_movement(
                self._catalog,
                business_id=ctx.business_id,
                entry_date=ctx.entry_date,
                cash_account_ref=ctx.cash_account_id,
                counter_account_ref=match.account_code,
                amount=ctx.amount,
                cash_movement=ctx.cash_movement,
                description=ctx.description,
                reason_code=match.reason_code,
                source=EscalationSource.RULE,
                confidence_score=match.confidence,
            )
        except DirectionConsistencyError as exc:
            logger.warning(
                "[ladder.rule] bank_txn=%s direction conflict (%s) -> review",
                ctx.bank_transaction_id, exc,
            )
            return self._forward(ctx)

        entry = self._posting.post(
            draft, decided_by="rule_engine", decision=ApprovalDecision.AUTO_APPROVED,
            notes=f"auto-posted by {match.reason_code}",
        )
        txn = self._bank_repo.get(ctx.bank_transaction_id)
        if txn is not None:
            self._bank_repo.mark_posted(txn, entry.id)
        logger.info(
            "[ladder.rule] AUTO-POSTED bank_txn=%s -> je=%s account=%s conf=%.2f",
            ctx.bank_transaction_id, entry.id, match.account_code, match.confidence,
        )
        return LadderOutcome(
            bank_transaction_id=ctx.bank_transaction_id,
            outcome="posted",
            journal_entry_id=entry.id,
            account_code=match.account_code,
            confidence=match.confidence,
            message=f"Auto-posted via {match.reason_code}.",
        )


class AgentHandler(EscalationHandler):
    """Judgment layer: when no rule matched, ask the classifier to pick an account.

    The proposal is *always* forwarded to review — the agent never posts. If a rule
    already produced a proposal (low-confidence / large), the agent stays out of the
    way and simply forwards.
    """

    def __init__(self, classifier: AccountClassifier, catalog: AccountCatalog,
                 leaves: List[AccountRecord]) -> None:
        super().__init__()
        self._classifier = classifier
        self._catalog = catalog
        self._leaves = leaves

    def handle(self, ctx: LadderContext) -> LadderOutcome:
        if ctx.proposal is not None:
            return self._forward(ctx)
        try:
            proposal = self._classifier.propose(ctx, self._leaves)
        except Exception as exc:  # a flaky model must not break the batch
            logger.warning("[ladder.agent] classifier error bank_txn=%s: %s",
                           ctx.bank_transaction_id, exc)
            proposal = None
        if proposal is not None:
            ctx.proposal = proposal
            logger.info("[ladder.agent] bank_txn=%s agent proposed account=%s conf=%.2f",
                        ctx.bank_transaction_id, proposal.account_code, proposal.confidence)
        else:
            logger.info("[ladder.agent] bank_txn=%s no agent proposal -> review",
                        ctx.bank_transaction_id)
        return self._forward(ctx)


class ReviewHandler(EscalationHandler):
    """Terminal layer: park the row in the unified review queue for a human."""

    def __init__(self, review_repo: ReviewItemRepository,
                 bank_repo: BankTransactionRepository) -> None:
        super().__init__()
        self._review_repo = review_repo
        self._bank_repo = bank_repo

    def handle(self, ctx: LadderContext) -> LadderOutcome:
        item_type = ReviewItemType.LARGE_AMOUNT if ctx.large_amount else ReviewItemType.UNCATEGORIZED
        source = ctx.proposal.source if ctx.proposal else EscalationSource.AGENT
        confidence = ctx.proposal.confidence if ctx.proposal else None
        proposed_resolution = None
        if ctx.proposal is not None:
            proposed_resolution = {
                "account_code": ctx.proposal.account_code,
                "reason_code": ctx.proposal.reason_code,
                "confidence": ctx.proposal.confidence,
                "cash_movement": ctx.cash_movement.value,
                "amount": str(ctx.amount),
            }

        item = self._review_repo.add(ReviewItem(
            business_id=ctx.business_id,
            item_type=item_type,
            status=ReviewStatus.OPEN,
            subject_type=SUBJECT_BANK_TRANSACTION,
            subject_id=ctx.bank_transaction_id,
            source=source,
            confidence=confidence,
            proposed_resolution=proposed_resolution,
        ))
        txn = self._bank_repo.get(ctx.bank_transaction_id)
        if txn is not None:
            self._bank_repo.mark_proposed(txn)
        logger.info(
            "[ladder.review] bank_txn=%s -> review_item=%s type=%s source=%s",
            ctx.bank_transaction_id, item.id, item_type.value, source.value,
        )
        return LadderOutcome(
            bank_transaction_id=ctx.bank_transaction_id,
            outcome="review",
            review_item_id=item.id,
            item_type=item_type.value,
            account_code=ctx.proposal.account_code if ctx.proposal else None,
            confidence=confidence,
            message=f"Escalated to review as {item_type.value}.",
        )
