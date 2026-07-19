"""Pydantic schemas for businesses, chart-of-accounts accounts, and parties."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.domain.enums import AccountType, NormalBalance
from app.domain.schemas.base import ORMModel


# --- Business -------------------------------------------------------------
class BusinessBase(BaseModel):
    name: str
    legal_name: Optional[str] = None
    business_type: Optional[str] = None
    currency: str = "USD"


class BusinessCreate(BusinessBase):
    pass


class BusinessOut(ORMModel, BusinessBase):
    id: int
    created_at: datetime
    updated_at: datetime


# --- Account (chart of accounts) ------------------------------------------
class AccountOut(ORMModel):
    """A chart-of-accounts node (read-only; the COA is seeded, not user-created)."""

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
    is_control_account: bool
    is_active: bool


# --- Vendor ---------------------------------------------------------------
class VendorBase(BaseModel):
    business_id: int
    name: str
    normalized_name: Optional[str] = None


class VendorCreate(VendorBase):
    pass


class VendorOut(ORMModel, VendorBase):
    id: int
    created_at: datetime


# --- Customer -------------------------------------------------------------
class CustomerBase(BaseModel):
    business_id: int
    name: str
    normalized_name: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(ORMModel, CustomerBase):
    id: int
    created_at: datetime
