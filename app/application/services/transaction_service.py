"""Transaction service — query and aggregation logic."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.enums import ReviewStatus, TransactionType
from app.domain.models import Transaction, Document


class TransactionService:
    """All business logic that operates on Transaction records.

    Usage:
        svc = TransactionService()
        summary = svc.get_summary(db, business_id)
    """

    def get_summary(
        self,
        db: Session,
        business_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Return aggregate totals for a business's transactions.

        Response shape:
        {
          "total_count": 42,
          "total_inflow": 12500.00,
          "total_outflow": 4300.00,
          "net": 8200.00,
          "needs_review_count": 10,
          "by_review_status": { "needs_review": 10, "auto_approved": 32 }
        }
        """
        # Transactions have no business_id — scope them through their document.
        q = (
            db.query(Transaction)
            .join(Document, Transaction.document_id == Document.id)
            .filter(Document.business_id == business_id)
        )
        if start_date is not None:
            q = q.filter(Transaction.date >= start_date)
        if end_date is not None:
            q = q.filter(Transaction.date <= end_date)

        transactions = q.all()

        # Direction now lives in trans_type: CREDIT = money in, DEBIT = money out.
        total_inflow: Decimal = sum(
            (t.amount for t in transactions if t.trans_type == TransactionType.CREDIT),
            Decimal("0"),
        )
        total_outflow: Decimal = sum(
            (t.amount for t in transactions if t.trans_type == TransactionType.DEBIT),
            Decimal("0"),
        )

        by_status: dict[str, int] = {}
        for t in transactions:
            key = t.review_status.value
            by_status[key] = by_status.get(key, 0) + 1

        return {
            "total_count": len(transactions),
            "total_inflow": float(total_inflow),
            "total_outflow": float(total_outflow),
            "net": float(total_inflow - total_outflow),
            "needs_review_count": by_status.get(ReviewStatus.NEEDS_REVIEW.value, 0),
            "by_review_status": by_status,
        }
