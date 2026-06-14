"""Schemas for generated P&L reports."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.base import ORMModel


class PnLReportBase(BaseModel):
    business_id: int
    period_start: date
    period_end: date
    revenue_total: Optional[Decimal] = None
    cogs_total: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    operating_expenses_total: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None
    report_json: Optional[Any] = None


class PnLReportCreate(PnLReportBase):
    pass


class PnLReportOut(ORMModel, PnLReportBase):
    id: int
    created_at: datetime
