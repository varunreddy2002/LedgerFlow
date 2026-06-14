"""Business CRUD endpoints.

Routes
------
GET  /api/businesses
GET  /api/businesses/{business_id}
POST /api/businesses

The ``get_business_or_404`` helper is also imported by other routers that
sit under /businesses/{business_id}/... so they can reuse the 404 guard
without duplicating the query.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.business import Business
from app.schemas import BusinessCreate, BusinessOut
from app.services.seeding_service import seed_business_defaults

router = APIRouter(prefix="/businesses", tags=["businesses"])


# ---------------------------------------------------------------------------
# Shared dependency — re-used by documents / transactions routers
# ---------------------------------------------------------------------------

def get_business_or_404(business_id: int, db: Session = Depends(get_db)) -> Business:
    """FastAPI dependency: resolve {business_id} path param → Business or 404."""
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business {business_id} not found",
        )
    return biz


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[BusinessOut])
def list_businesses(db: Session = Depends(get_db)):
    """Return all businesses (no auth yet — multi-tenant guard comes later)."""
    return db.query(Business).order_by(Business.id).all()


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(business: Business = Depends(get_business_or_404)):
    return business


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    biz = Business(**payload.model_dump())
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


@router.post("/{business_id}/setup", status_code=status.HTTP_200_OK)
def setup_business_defaults(
    business: Business = Depends(get_business_or_404),
    db: Session = Depends(get_db),
):
    """Seed default categories and generic categorization rules for a business.

    Call this once after creating a business and configuring accounts.
    Safe to call multiple times — skips anything already seeded.
    """
    seed_business_defaults(db, business.id)
    db.commit()
    return {"message": f"Default categories and rules seeded for business '{business.name}'."}
