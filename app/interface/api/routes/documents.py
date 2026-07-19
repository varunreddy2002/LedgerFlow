"""Document retrieval endpoints.

NOTE: file-upload ingestion (CSV/PDF → bank_transactions/bills/invoices) is
intentionally dormant during the ledger-core rebuild — the escalation ladder is
fed from *seeded* ``bank_transactions`` instead (see docs/HANDOVER.md). The upload
endpoint therefore returns 501 until ingestion is repointed at the new schema.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.domain.schemas import DocumentOut

from app.interface.api.routes.businesses import get_business_or_404
from app.infrastructure.db.database import get_db
from app.domain.models import Business, Document


router = APIRouter(tags=["documents"])

@router.get("/businesses/{business_id}/documents", response_model=list[DocumentOut])
def list_documents(
    business_id: int,
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    return (
        db.query(Document)
        .filter(Document.business_id == business_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc

@router.post(
    "/businesses/{business_id}/documents/upload",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def upload_document(
    business_id: int,
    file: UploadFile = File(...),
    _: Business = Depends(get_business_or_404),
):
    """Dormant during the ledger-core rebuild — feed the ladder via seeded
    ``bank_transactions`` instead. Returns 501 until ingestion is repointed."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "File ingestion is temporarily disabled during the ledger-core "
            "rebuild. Seed bank_transactions via /businesses/{id}/setup instead."
        ),
    )
