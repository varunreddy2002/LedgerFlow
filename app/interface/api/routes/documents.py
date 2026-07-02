"""Document upload and retrieval endpoints."""

from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from app.domain.schemas import DocumentOut, UploadResponse
from app.application.services import run_ingestion
from app.domain.enums import DocumentStatus

from app.interface.api.routes.businesses import get_business_or_404
from app.infrastructure.db.database import get_db
from app.domain.models import Business, Document


router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS: set[str] = {".csv", ".pdf"}

"""
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
"""

@router.post(
    "/businesses/{business_id}/documents/upload",
    status_code=status.HTTP_202_ACCEPTED
)
async def upload_document(
    business_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Unsupported file type '{ext}'")
    
    content = await file.read()
    background_tasks.add_task(run_ingestion, business_id, file.filename, content, ext)
    return UploadResponse(status=DocumentStatus.PROCESSING)
