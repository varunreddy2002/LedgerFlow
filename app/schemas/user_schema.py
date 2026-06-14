"""Schemas for application users."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.schemas.base import ORMModel


class UserBase(BaseModel):
    business_id: int
    name: str
    email: str
    is_active: bool = True


class UserCreate(UserBase):
    pass


class UserOut(ORMModel, UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
