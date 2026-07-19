"""The categorization pipeline — wires and runs the escalation ladder.

`CategorizationPipeline` owns the chain head and turns bank rows into contexts. The
:func:`build_pipeline` factory assembles the chain (Rule → Agent → Review) with all
dependencies bound to one session, reading thresholds from ``settings`` (wiring the
previously-dead ``large_transaction_threshold``).
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import AccountType, BankTxnStatus
from app.domain.models.ledger import BankTransaction
from app.application.accounting.journal_entry_builder import AccountCatalog
from app.application.accounting.posting_service import PostingService
from app.application.accounting.repository import (
    BankTransactionRepository,
    ReviewItemRepository,
    SqlAlchemyLedgerRepository,
)
from app.application.accounting.rule_engine import AccountingRuleEngine, load_rules
from app.application.accounting.escalation.context import (
    AccountClassifier,
    LadderContext,
    LadderOutcome,
    NullAccountClassifier,
)
from app.application.accounting.escalation.handlers import (
    AgentHandler,
    EscalationHandler,
    RuleHandler,
    ReviewHandler,
)

logger = get_logger(__name__)


class CategorizationPipeline:
    """Runs the escalation ladder over a business's unprocessed bank rows."""

    def __init__(
        self,
        session: Session,
        business_id: int,
        head: EscalationHandler,
        bank_repo: BankTransactionRepository,
    ) -> None:
        self._session = session
        self._business_id = business_id
        self._head = head
        self._bank_repo = bank_repo

    def process_one(self, txn: BankTransaction) -> LadderOutcome:
        """Run the ladder on a single bank row."""
        ctx = LadderContext(
            bank_transaction_id=txn.id,
            business_id=txn.business_id,
            cash_account_id=txn.gl_account_id,
            description=txn.description or "",
            amount=txn.amount,
            cash_movement=txn.cash_movement,
            entry_date=txn.transaction_date,
        )
        return self._head.handle(ctx)

    def run(self, limit: Optional[int] = None) -> List[LadderOutcome]:
        """Process all UNPROCESSED bank rows; return per-row outcomes."""
        rows = self._bank_repo.list_by_status(self._business_id, BankTxnStatus.UNPROCESSED)
        if limit is not None:
            rows = rows[:limit]
        outcomes = [self.process_one(txn) for txn in rows]
        posted = sum(1 for o in outcomes if o.outcome == "posted")
        review = sum(1 for o in outcomes if o.outcome == "review")
        logger.info(
            "[pipeline] business_id=%s processed=%d auto_posted=%d review=%d",
            self._business_id, len(outcomes), posted, review,
        )
        return outcomes


def build_pipeline(
    session: Session,
    business_id: int,
    *,
    classifier: Optional[AccountClassifier] = None,
) -> CategorizationPipeline:
    """Assemble the ladder for a business, bound to ``session``.

    ``classifier`` defaults to a no-op (deterministic, no LLM needed) so the pipeline
    runs anywhere; pass a real :class:`AccountClassifier` (e.g. Bedrock) to have the
    agent layer propose accounts for unmatched rows.
    """
    ledger_repo = SqlAlchemyLedgerRepository(session)
    records = ledger_repo.list_accounts(business_id)
    catalog = AccountCatalog.from_records(records)
    leaves = [
        r for r in records
        if r.posting_allowed and r.account_type in (AccountType.REVENUE, AccountType.EXPENSE)
    ]

    bank_repo = BankTransactionRepository(session)
    review_repo = ReviewItemRepository(session)
    posting = PostingService(session)
    rule_engine = AccountingRuleEngine(load_rules(session, business_id))

    rule_handler = RuleHandler(
        rule_engine, catalog, posting, bank_repo,
        confidence_threshold=settings.categorization_confidence_threshold,
        large_amount_threshold=settings.large_transaction_threshold,
    )
    agent_handler = AgentHandler(classifier or NullAccountClassifier(), catalog, leaves)
    review_handler = ReviewHandler(review_repo, bank_repo)

    # Chain: Rule → Agent → Review.
    rule_handler.set_next(agent_handler).set_next(review_handler)

    logger.info(
        "[pipeline] built for business_id=%s rules=%d leaves=%d classifier=%s",
        business_id, len(rule_engine._rules), len(leaves),
        type(classifier or NullAccountClassifier()).__name__,
    )
    return CategorizationPipeline(session, business_id, rule_handler, bank_repo)
