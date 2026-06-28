from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.domain.enums import ReviewStatus, TransactionType
from app.domain.schemas.base import ORMModel


class TransactionOut(ORMModel):
    id: int
    document_id: Optional[int] = None
    party_id: Optional[int] = None
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None
    date: date
    due_date: Optional[date] = None
    amount: Decimal
    trans_type: TransactionType
    category_id: Optional[int] = None
    review_status: ReviewStatus
    fingerprint_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None
    review_status: Optional[ReviewStatus] = None


class TransactionLineItemOut(ORMModel):
    id: int
    transaction_id: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    category_id: Optional[int] = None
    review_status: ReviewStatus
    created_at: datetime
