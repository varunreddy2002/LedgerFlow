"""Document upload and retrieval endpoints.

Routes
------
GET  /api/businesses/{business_id}/documents
POST /api/businesses/{business_id}/documents/upload
GET  /api/documents/{document_id}

Upload flow
-----------
1. Validate file extension (.csv or .pdf only).
2. Read file into memory and compute SHA-256 checksum.
3. Check for duplicate file (same business + same checksum).
   → If duplicate: return existing document info without storing again.
4. Save file to  uploads/{business_id}/{uuid}.{ext}
5. Create ``documents`` row (flushed so doc.id is available).
6. If CSV: parse rows → Transaction rows → bulk insert → mark doc processed.
   If PDF:  leave status as pending_ocr (OCR pipeline not yet built).
7. Commit and return UploadResponse with parse summary.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.routes.businesses import get_business_or_404
from app.db.database import get_db
from app.models.business import Business
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.transaction import Transaction
from app.schemas.document import DocumentOut, ParseErrorDetail, UploadResponse
from app.services import csv_parser, document_service

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS: set[str] = {".csv", ".pdf"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/documents", response_model=list[DocumentOut])
def list_documents(
    business_id: int,
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    """List all uploaded documents for a business, newest first."""
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
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Business = Depends(get_business_or_404),
):
    """Upload a CSV or PDF financial file for a business.

    - CSV files are parsed immediately; transactions are created in the same request.
    - PDF files are stored and marked ``pending_ocr`` (pipeline not yet active).
    - Uploading the same file twice returns the existing document without
      creating duplicates (checked via SHA-256 checksum).
    """
    # --- Extension check ---------------------------------------------------
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Please upload a .csv or .pdf file.",
        )

    # --- Read + checksum ---------------------------------------------------
    content, checksum = await document_service.read_and_checksum(file)

    # --- Duplicate file guard ----------------------------------------------
    existing = document_service.get_by_checksum(db, business_id, checksum)
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

    # --- Save to disk ------------------------------------------------------
    stored_filename, file_path = document_service.save_to_disk(content, business_id, filename)

    # --- Create document row (flushed, not committed yet) ------------------
    doc = document_service.create_document(
        db,
        business_id=business_id,
        original_filename=filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size=len(content),
        checksum=checksum,
        file_ext=ext,
    )

    # --- CSV parsing -------------------------------------------------------
    rows_imported = 0
    rows_skipped = 0
    dup_txns = 0
    parse_errors: list[ParseErrorDetail] = []

    if ext == ".csv":
        # Collect fingerprints already in DB for this business so re-uploads
        # of individual rows are caught even across different files.
        existing_fps: set[str] = {
            fp
            for (fp,) in db.query(Transaction.fingerprint_hash).filter(
                Transaction.business_id == business_id,
                Transaction.fingerprint_hash.isnot(None),
            )
        }

        result = csv_parser.parse_csv(
            file_content=content,
            business_id=business_id,
            document_id=doc.id,
            existing_fingerprints=existing_fps,
        )

        if result.transactions:
            db.add_all(result.transactions)

        # Mark doc processed only when parsing had no fatal errors
        if not any(e.row_number == 0 for e in result.errors):
            doc.status = DocumentStatus.processed

        rows_imported = result.rows_imported
        rows_skipped = result.rows_skipped
        dup_txns = result.duplicate_fingerprints
        parse_errors = [
            ParseErrorDetail(
                row_number=e.row_number,
                reason=e.reason,
                raw_value=e.raw_value,
            )
            for e in result.errors
        ]

    # --- Commit everything -------------------------------------------------
    db.commit()
    db.refresh(doc)

    msg = (
        f"File uploaded and parsed: {rows_imported} transactions imported, "
        f"{rows_skipped} rows skipped."
        if ext == ".csv"
        else "File uploaded. PDF is queued for OCR processing."
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
