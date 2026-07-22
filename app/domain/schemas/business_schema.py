"""Schemas for businesses and the chart of accounts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.domain.enums import AccountType, NormalBalance
from app.domain.schemas.base import ORMModel


# --- Business -------------------------------------------------------------
class BusinessBase(BaseModel):
    name: str
    business_type: Optional[str] = None
    currency: str = "USD"


class BusinessCreate(BusinessBase):
    pass


class BusinessOut(ORMModel, BusinessBase):
    id: int
    created_at: datetime
    updated_at: datetime


# --- Account ----------------------------------------------------------------
# Read-only: accounts are the chart of accounts, created only by seeding
# (POST /businesses/{id}/setup), not through a create-account API.
class AccountOut(ORMModel):
    id: int
    business_id: int
    account_code: str
    account_name: str
    account_type: AccountType
    account_subtype: Optional[str] = None
    parent_account_id: Optional[int] = None
    hierarchy_level: int
    normal_balance: NormalBalance
    posting_allowed: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
