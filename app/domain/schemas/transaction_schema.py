from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, model_validator

from app.domain.enums import ReviewStatus, TransactionType
from app.domain.schemas.base import ORMModel


class TransactionOut(ORMModel):
    id: int
    document_id: Optional[int] = None
    date: date
    due_date: Optional[date] = None
    description: Optional[str] = None
    amount: Decimal
    trans_type: TransactionType
    review_status: ReviewStatus
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_names(cls, obj: Any) -> Any:
        if not hasattr(obj, "__dict__"):
            return obj
        if obj.category is not None:
            obj.__dict__.setdefault("category_name", obj.category.name)
        if obj.vendor is not None:
            obj.__dict__.setdefault("vendor_name", obj.vendor.name)
        if obj.customer is not None:
            obj.__dict__.setdefault("customer_name", obj.customer.name)
        return obj


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
