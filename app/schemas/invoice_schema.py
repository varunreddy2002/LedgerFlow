from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[Decimal] = None
    amount: Decimal
    is_tax_line: bool = False


class InvoicePageExtraction(BaseModel):
    schema_version: str = "v1"
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    line_items: list[LineItem] = []
    total_amount: Optional[Decimal] = None


class InvoiceExtraction(BaseModel):
    schema_version: str = "v1"
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    line_items: list[LineItem] = []
    total_amount: Optional[Decimal] = None
