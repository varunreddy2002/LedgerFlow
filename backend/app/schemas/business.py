"""Schemas for businesses, accounts, categories, vendors and customers."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import AccountType, CategoryType
from app.schemas.base import ORMModel


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


# --- Account --------------------------------------------------------------
class AccountBase(BaseModel):
    business_id: int
    account_name: str
    account_type: AccountType
    institution_name: Optional[str] = None
    last_four: Optional[str] = None
    currency: str = "USD"


class AccountCreate(AccountBase):
    pass


class AccountOut(ORMModel, AccountBase):
    id: int
    created_at: datetime


# --- Category -------------------------------------------------------------
class CategoryBase(BaseModel):
    business_id: int
    name: str
    parent_category_id: Optional[int] = None
    category_type: CategoryType
    is_system: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(ORMModel, CategoryBase):
    id: int
    created_at: datetime


# --- Vendor ---------------------------------------------------------------
class VendorBase(BaseModel):
    business_id: int
    name: str
    normalized_name: Optional[str] = None
    default_category_id: Optional[int] = None
    vendor_type: Optional[str] = None


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
    source: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(ORMModel, CustomerBase):
    id: int
    created_at: datetime
