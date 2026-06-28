"""Account endpoints.

Routes
------
GET  /api/businesses/{business_id}/accounts
POST /api/businesses/{business_id}/accounts
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.interface.api.routes.businesses import get_business_or_404
from app.infrastructure.db.database import get_db
from app.domain.models import Account, Business
from app.domain.schemas import AccountCreate, AccountOut

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


@router.post(
    "/businesses/{business_id}/accounts",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    business_id: int,
    payload: AccountCreate,
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    """Add a new account to a business.

    ``business_id`` is taken from the URL — any value in the request body
    is ignored and overridden by the path parameter.
    """
    acct = Account(**{**payload.model_dump(), "business_id": business_id})
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct
