"""Categorization service — assigns categories to transactions after import."""

import logging
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.db.database import SessionLocal
from app.domain.models import Document, CategorizationRule, Transaction
from app.domain.enums import DocumentStatus, ReviewStatus, TransactionType

logger = logging.getLogger(__name__)


class CategorizationService:
    """Loads rules once, then matches transactions against them.

    Usage:
        service = CategorizationService(db, business_id)
        service.run(document_id)
    """

    def __init__(self, db: Session, business_id: int) -> None:
        self.db = db
        self.business_id = business_id
        self.threshold = settings.categorization_confidence_threshold
        self._compiled_rules = self._load_rules()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, document_id: int) -> None:
        """Categorize all uncategorized transactions for a document."""
        transactions = self._pending_transactions(document_id)

        if not transactions:
            logger.debug("No uncategorized transactions for document_id=%s.", document_id)
            self._mark_processed(document_id)
            return

        if not self._compiled_rules:
            logger.info("No rules for business_id=%s — skipping.", self.business_id)
            self._mark_processed(document_id)
            return

        matched = sum(1 for txn in transactions if self._match(txn))

        logger.info(
            "Categorization done for document_id=%s: %d/%d matched.",
            document_id, matched, len(transactions),
        )

        self.db.flush()
        self._mark_processed(document_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_rules(self) -> list[tuple[re.Pattern, CategorizationRule]]:
        """Load and compile all regex rules for this business."""
        rules = (
            self.db.query(CategorizationRule)
            .filter(CategorizationRule.business_id == self.business_id)
            .order_by(CategorizationRule.confidence_boost.desc().nullslast())
            .all()
        )
        compiled = []
        for rule in rules:
            try:
                compiled.append((re.compile(rule.merchant_pattern, re.IGNORECASE), rule))
            except re.error:
                logger.warning("Invalid regex in rule id=%s pattern='%s'", rule.id, rule.merchant_pattern)
        return compiled

    def _match(self, txn: Transaction) -> bool:
        """Match one transaction against all rules. Returns True if matched."""
        description = txn.description_raw or ""
        for pattern, rule in self._compiled_rules:
            if pattern.search(description):
                txn.category_id = rule.category_id
                txn.transaction_type = rule.transaction_type or TransactionType.UNKNOWN
                txn.confidence_score = rule.confidence_boost or 0.0
                if txn.confidence_score >= self.threshold:
                    txn.review_status = ReviewStatus.AUTO_APPROVED
                return True
        return False

    def _pending_transactions(self, document_id: int) -> list[Transaction]:
        return (
            self.db.query(Transaction)
            .filter(
                Transaction.document_id == document_id,
                Transaction.business_id == self.business_id,
                Transaction.review_status == ReviewStatus.NEEDS_REVIEW,
                Transaction.category_id.is_(None),
            )
            .all()
        )

    def _mark_processed(self, document_id: int) -> None:
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.PROCESSED
            self.db.commit()


# ---------------------------------------------------------------------------
# BackgroundTask entry point — thin wrapper around the service class
# ---------------------------------------------------------------------------

def categorize_transactions(business_id: int, document_id: int) -> None:
    """Called by FastAPI BackgroundTasks after CSV upload or OCR completes."""
    db: Session = SessionLocal()
    try:
        CategorizationService(db, business_id).run(document_id)
    except Exception:
        logger.exception(
            "Categorization failed for document_id=%s business_id=%s",
            document_id, business_id,
        )
        db.rollback()
    finally:
        db.close()
