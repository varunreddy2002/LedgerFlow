"""Schemas for transactions, duplicate groups, review items and categorization rules."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.models.enums import (
    Direction,
    DuplicateGroupStatus,
    DuplicateMatchType,
    DuplicateResolution,
    ReviewIssueType,
    ReviewItemStatus,
    ReviewStatus,
    TransactionType,
)
from app.schemas.base import ORMModel


# --- Transaction ----------------------------------------------------------
class TransactionBase(BaseModel):
    business_id: int
    document_id: Optional[int] = None
    account_id: Optional[int] = None
    transaction_date: date
    posted_date: Optional[date] = None
    description_raw: Optional[str] = None
    description_clean: Optional[str] = None
    merchant_name: Optional[str] = None
    amount: Decimal
    direction: Direction
    category_id: Optional[int] = None
    customer_id: Optional[int] = None
    vendor_id: Optional[int] = None
    transaction_type: TransactionType = TransactionType.UNKNOWN
    confidence_score: Optional[float] = None
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    fingerprint_hash: Optional[str] = None
    is_excluded_from_pnl: bool = False
    exclusion_reason: Optional[str] = None
    notes: Optional[str] = None


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    """Partial update used during the review workflow — all fields optional."""

    category_id: Optional[int] = None
    customer_id: Optional[int] = None
    vendor_id: Optional[int] = None
    transaction_type: Optional[TransactionType] = None
    review_status: Optional[ReviewStatus] = None
    is_excluded_from_pnl: Optional[bool] = None
    exclusion_reason: Optional[str] = None
    notes: Optional[str] = None


class TransactionOut(ORMModel, TransactionBase):
    id: int
    created_at: datetime
    updated_at: datetime


# --- DuplicateGroup -------------------------------------------------------
class DuplicateGroupBase(BaseModel):
    business_id: int
    fingerprint_hash: str
    match_type: DuplicateMatchType
    match_score: Optional[float] = None
    status: DuplicateGroupStatus = DuplicateGroupStatus.PENDING_REVIEW
    resolution: Optional[DuplicateResolution] = None
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: Optional[int] = None
    notes: Optional[str] = None


class DuplicateGroupCreate(DuplicateGroupBase):
    pass


class DuplicateGroupOut(ORMModel, DuplicateGroupBase):
    id: int
    created_at: datetime
    updated_at: datetime


# --- DuplicateGroupMember -------------------------------------------------
class DuplicateGroupMemberBase(BaseModel):
    group_id: int
    transaction_id: int
    is_primary: bool = False
    is_kept: Optional[bool] = None  # null=unresolved, True=keep, False=exclude


class DuplicateGroupMemberCreate(DuplicateGroupMemberBase):
    pass


class DuplicateGroupMemberOut(ORMModel, DuplicateGroupMemberBase):
    id: int
    created_at: datetime


# --- ReviewItem -----------------------------------------------------------
class ReviewItemBase(BaseModel):
    business_id: int
    transaction_id: Optional[int] = None
    duplicate_group_id: Optional[int] = None
    issue_type: ReviewIssueType
    question: Optional[str] = None
    suggested_action: Optional[str] = None
    status: ReviewItemStatus = ReviewItemStatus.OPEN
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: Optional[int] = None


class ReviewItemCreate(ReviewItemBase):
    pass


class ReviewItemOut(ORMModel, ReviewItemBase):
    id: int
    created_at: datetime


# --- CategorizationRule ---------------------------------------------------
class CategorizationRuleBase(BaseModel):
    business_id: int
    merchant_pattern: str
    category_id: Optional[int] = None
    transaction_type: Optional[TransactionType] = None
    confidence_boost: Optional[float] = None


class CategorizationRuleCreate(CategorizationRuleBase):
    pass


class CategorizationRuleOut(ORMModel, CategorizationRuleBase):
    id: int
    created_at: datetime
