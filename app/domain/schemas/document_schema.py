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


class UploadResponse(BaseModel):
    """Document upload response"""
    status: DocumentStatus
    
from pydantic import BaseModel, Field

class CSVColumnMapping(BaseModel):
    date: str | None = Field(None, description="the date when the transaction was posted or occurred")
    description: str | None = Field(None, description="the narration or merchant name or transaction description")
    amount: str | None = Field(None, description="the transaction amount, can be negative for debits")
    trans_type: str | None = Field(None, description="indicates if the transaction is a debit or credit")

class DocumentLineItem(BaseModel):
    description: str | None = Field(None, description="the item or service name")
    quantity: float | None = Field(None, description="quantity of the item")
    net_price: float | None = Field(None, description="price per single unit before tax")
    tax_amount: float | None = Field(None, description="tax charged on this line item, if any")


class ExtractedDocument(BaseModel):
    seller_name: str | None = Field(None, description="the party who issued the document (the seller / vendor)")
    buyer_name: str | None = Field(None, description="the party being billed (the buyer / bill-to / customer)")
    invoice_number: str | None = Field(None, description="the invoice or bill number")
    invoice_date: str | None = Field(None, description="issue date in YYYY-MM-DD format")
    due_date: str | None = Field(None, description="payment due date in YYYY-MM-DD format")
    total_amount: float | None = Field(None, description="the grand total amount of the document")
    tax_amount: float | None = Field(None, description="the total tax amount of the document")
    line_items: list[DocumentLineItem] = Field(default_factory=list, description="all line items in the document")

class ParseErrorDetail(BaseModel):
    row_number: int
    reason: str
    raw_value: str = ""




# Not required below ones

"""
class UploadResponse(BaseModel):
    document: DocumentOut
    is_duplicate_file: bool
    duplicate_document_id: Optional[int] = None
    message: str
    rows_imported: int = 0
    rows_skipped: int = 0
    duplicate_transactions: int = 0
    parse_errors: list[ParseErrorDetail] = []
"""