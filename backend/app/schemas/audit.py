"""Schemas for audit-log entries."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.base import ORMModel


class AuditLogBase(BaseModel):
    business_id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogOut(ORMModel, AuditLogBase):
    id: int
    created_at: datetime
