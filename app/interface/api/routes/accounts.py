"""Chart-of-accounts read endpoints.

The COA is seeded (see ``seeding_service``), not user-created, so this router is
read-only: it lists a business's accounts ordered by code for inspection and for
the frontend account picker.

Routes
------
GET /api/businesses/{business_id}/accounts
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
    """List a business's chart of accounts, ordered by account code."""
    return (
        db.query(Account)
        .filter(Account.business_id == business_id)
        .order_by(Account.account_code)
        .all()
    )
