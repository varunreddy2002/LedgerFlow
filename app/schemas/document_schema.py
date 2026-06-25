"""Schemas for documents and their extractions."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus, SourceType
from app.schemas.base import ORMModel


# --- Document -------------------------------------------------------------
class DocumentBase(BaseModel):
    business_id: int
    original_filename: str
    stored_filename: str
    file_type: Optional[str] = None
    file_path: str
    file_size: Optional[int] = None
    sha256_checksum: str
    source_type: SourceType = SourceType.UNKNOWN
    status: DocumentStatus = DocumentStatus.UPLOADED


class DocumentCreate(DocumentBase):
    pass


class DocumentOut(ORMModel, DocumentBase):
    id: int
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None


# --- Upload response ------------------------------------------------------

class ParseErrorDetail(BaseModel):
    row_number: int
    reason: str
    raw_value: str = ""


class UploadResponse(BaseModel):
    """Returned by POST /businesses/{id}/documents/upload."""

    document: DocumentOut
    is_duplicate_file: bool
    duplicate_document_id: Optional[int] = None
    message: str
    # CSV-only fields (0 for PDFs)
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_transactions: int = 0
    parse_errors: list[ParseErrorDetail] = []


# --- DocumentExtraction ---------------------------------------------------
class DocumentExtractionBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    document_id: int
    extraction_type: Optional[str] = None
    raw_text: Optional[str] = None
    extracted_json: Optional[Any] = None
    model_used: Optional[str] = None
    confidence_score: Optional[float] = None


class DocumentExtractionCreate(DocumentExtractionBase):
    pass


class DocumentExtractionOut(ORMModel, DocumentExtractionBase):
    id: int
    created_at: datetime
