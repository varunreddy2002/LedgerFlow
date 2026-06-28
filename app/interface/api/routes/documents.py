"""Document upload and retrieval endpoints."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.interface.api.routes.businesses import get_business_or_404
from app.infrastructure.db.database import get_db
from app.domain.models import Business, Document
from app.domain.enums import DocumentStatus
from app.domain.schemas import DocumentOut, ParseErrorDetail, UploadResponse
from app.application.services import csv_parser
from app.application.services.categorization_service import categorize_transactions
from app.infrastructure.storage.document_storage import DocumentService
from app.application.services.ocr_service import process_pdf_document

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS: set[str] = {".csv", ".pdf"}

_doc_service = DocumentService()


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
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_document(
    business_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Please upload a .csv or .pdf file.",
        )

    content, checksum = await _doc_service.read_and_checksum(file)

    existing = _doc_service.get_by_checksum(db, business_id, checksum)
    if existing:
        return UploadResponse(
            document=DocumentOut.model_validate(existing),
            is_duplicate_file=True,
            duplicate_document_id=existing.id,
            message=(
                f"This file has already been uploaded "
                f"(existing document id={existing.id}, "
                f"original name='{existing.original_filename}')."
            ),
        )

    stored_filename, file_path = _doc_service.save_to_disk(content, business_id, filename)

    doc = _doc_service.create_document(
        db,
        business_id=business_id,
        original_filename=filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size=len(content),
        checksum=checksum,
        file_ext=ext,
    )

    rows_imported = 0
    rows_skipped = 0
    dup_txns = 0
    parse_errors: list[ParseErrorDetail] = []

    if ext == ".csv":
        existing_fps = _doc_service.get_existing_fingerprints(db, business_id)

        result = csv_parser.parse_csv(
            file_content=content,
            business_id=business_id,
            document_id=doc.id,
            existing_fingerprints=existing_fps,
        )

        if result.transactions:
            db.add_all(result.transactions)

        _doc_service.apply_csv_status(doc, result)

        rows_imported = result.rows_imported
        rows_skipped = result.rows_skipped
        dup_txns = result.duplicate_fingerprints
        parse_errors = [
            ParseErrorDetail(row_number=e.row_number, reason=e.reason, raw_value=e.raw_value)
            for e in result.errors
        ]

    db.commit()
    db.refresh(doc)

    if ext == ".csv" and doc.status == DocumentStatus.CATEGORIZING:
        background_tasks.add_task(categorize_transactions, business_id, doc.id)

    if ext == ".pdf":
        background_tasks.add_task(process_pdf_document, doc.id, business_id)


    msg = (
        f"File uploaded and parsed: {rows_imported} transactions imported, "
        f"{rows_skipped} rows skipped."
        if ext == ".csv"
        else "File uploaded. PDF queued for OCR — transactions will appear shortly."
    )

    return UploadResponse(
        document=DocumentOut.model_validate(doc),
        is_duplicate_file=False,
        message=msg,
        rows_imported=rows_imported,
        rows_skipped=rows_skipped,
        duplicate_transactions=dup_txns,
        parse_errors=parse_errors,
    )
