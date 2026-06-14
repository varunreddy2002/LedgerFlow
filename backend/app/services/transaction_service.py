"""Transaction service — query and aggregation logic."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.enums import Direction, ReviewStatus
from app.models.transaction import Transaction


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
        """Return aggregate totals for non-excluded transactions.

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
        q = db.query(Transaction).filter(
            Transaction.business_id == business_id,
            Transaction.is_excluded_from_pnl == False,  # noqa: E712
        )
        if start_date is not None:
            q = q.filter(Transaction.transaction_date >= start_date)
        if end_date is not None:
            q = q.filter(Transaction.transaction_date <= end_date)

        transactions = q.all()

        total_inflow: Decimal = sum(
            (t.amount for t in transactions if t.direction == Direction.INFLOW),
            Decimal("0"),
        )
        total_outflow: Decimal = sum(
            (t.amount for t in transactions if t.direction == Direction.OUTFLOW),
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
