"""Transaction read and update endpoints.

Routes
------
GET   /api/businesses/{business_id}/transactions          — filtered list
GET   /api/businesses/{business_id}/transactions/summary  — aggregate counts
GET   /api/transactions/{transaction_id}                  — single record
PATCH /api/transactions/{transaction_id}                  — review-time update

Pagination
----------
All list endpoints accept ``limit`` (max 500, default 100) and ``offset``
query parameters.  Rows are ordered newest-date-first.

PATCH behaviour
---------------
- Only fields present in the request body are updated (partial update).
- When ``category_id`` changes and the caller did not explicitly set
  ``review_status``, the status is automatically bumped to ``user_corrected``
  so the review queue knows a human acted on this row.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.routes.businesses import get_business_or_404
from app.db.database import get_db
from app.models.business import Business
from app.models.enums import Direction, ReviewStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas import TransactionOut, TransactionUpdate

router = APIRouter(tags=["transactions"])


# ---------------------------------------------------------------------------
# List + filters
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/transactions", response_model=list[TransactionOut])
def list_transactions(
    business_id: int,
    # --- filters ---
    review_status: Optional[ReviewStatus] = None,
    category_id: Optional[int] = None,
    direction: Optional[Direction] = None,
    transaction_type: Optional[TransactionType] = None,
    is_excluded_from_pnl: Optional[bool] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    # --- pagination ---
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    q = db.query(Transaction).filter(Transaction.business_id == business_id)

    if review_status is not None:
        q = q.filter(Transaction.review_status == review_status)
    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)
    if direction is not None:
        q = q.filter(Transaction.direction == direction)
    if transaction_type is not None:
        q = q.filter(Transaction.transaction_type == transaction_type)
    if is_excluded_from_pnl is not None:
        q = q.filter(Transaction.is_excluded_from_pnl == is_excluded_from_pnl)
    if start_date is not None:
        q = q.filter(Transaction.transaction_date >= start_date)
    if end_date is not None:
        q = q.filter(Transaction.transaction_date <= end_date)

    return (
        q.order_by(Transaction.transaction_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Summary — must be registered BEFORE /{transaction_id} so FastAPI doesn't
# try to parse "summary" as an integer path parameter.
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/transactions/summary")
def transaction_summary(
    business_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    """Return aggregate totals for transactions that are included in P&L.

    Response shape:
    ```json
    {
      "total_count": 42,
      "total_inflow": 12500.00,
      "total_outflow": 4300.00,
      "net": 8200.00,
      "needs_review_count": 10,
      "by_review_status": { "needs_review": 10, "auto_approved": 32 }
    }
    ```
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
        (t.amount for t in transactions if t.direction == Direction.inflow),
        Decimal("0"),
    )
    total_outflow: Decimal = sum(
        (t.amount for t in transactions if t.direction == Direction.outflow),
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


# ---------------------------------------------------------------------------
# Single record
# ---------------------------------------------------------------------------

@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )
    return txn


# ---------------------------------------------------------------------------
# Partial update (review-time corrections)
# ---------------------------------------------------------------------------

@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
):
    """Apply a partial update to a transaction.

    Intended for the review workflow: a user corrects a category, sets a
    vendor, or excludes a row from P&L.  Any field omitted in the request
    body is left unchanged.

    Auto-rule: if ``category_id`` changes and the caller did not supply a
    ``review_status``, the status is set to ``user_corrected`` automatically.
    """
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )

    updates = payload.model_dump(exclude_unset=True)

    # Auto-bump review_status when the user changes the category
    if (
        "category_id" in updates
        and updates["category_id"] != txn.category_id
        and "review_status" not in updates
    ):
        updates["review_status"] = ReviewStatus.USER_CORRECTED

    for attr, value in updates.items():
        setattr(txn, attr, value)

    db.commit()
    db.refresh(txn)
    return txn
