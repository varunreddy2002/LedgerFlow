from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.domain.enums import DocumentStatus, SourceType
from app.domain.schemas.base import ORMModel


class DocumentOut(ORMModel):
    id: int
    business_id: int
    party_id: Optional[int] = None
    source: SourceType
    filename: str
    file_path: str
    sha256_checksum: str
    status: DocumentStatus
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ParseErrorDetail(BaseModel):
    row_number: int
    reason: str
    raw_value: str = ""


class UploadResponse(BaseModel):
    document: DocumentOut
    is_duplicate_file: bool
    duplicate_document_id: Optional[int] = None
    message: str
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_transactions: int = 0
    parse_errors: list[ParseErrorDetail] = []


class DocumentExtractionOut(ORMModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    document_id: int
    extraction_type: Optional[str] = None
    raw_text: Optional[str] = None
    extracted_json: Optional[Any] = None
    model_used: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime
