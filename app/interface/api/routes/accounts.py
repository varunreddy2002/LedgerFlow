"""Account endpoints.

Routes
------
GET  /api/businesses/{business_id}/accounts

Accounts are the chart of accounts — created only by seeding
(POST /businesses/{id}/setup), not through this API. There's no
create-account endpoint: ad hoc COA edits aren't a designed feature yet.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.interface.api.routes.businesses import get_business_or_404
from app.infrastructure.db.database import get_db
from app.domain.models import Account, Business
from app.domain.schemas import AccountOut

router = APIRouter(tags=["accounts"])


@router.get("/businesses/{business_id}/accounts", response_model=list[AccountOut])
def list_accounts(
    business_id: int,
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    """List all accounts for a business."""
    return (
        db.query(Account)
        .filter(Account.business_id == business_id)
        .order_by(Account.id)
        .all()
    )
