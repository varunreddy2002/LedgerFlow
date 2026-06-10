"""Schemas for transactions, duplicate candidates, review items and rules."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.models.enums import (
    Direction,
    DuplicateMatchType,
    DuplicateStatus,
    ResolvedAction,
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
    transaction_type: TransactionType = TransactionType.unknown
    confidence_score: Optional[float] = None
    review_status: ReviewStatus = ReviewStatus.needs_review
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


# --- DuplicateCandidate ---------------------------------------------------
class DuplicateCandidateBase(BaseModel):
    business_id: int
    transaction_id_1: int
    transaction_id_2: int
    match_type: DuplicateMatchType
    match_score: Optional[float] = None
    reason: Optional[str] = None
    status: DuplicateStatus = DuplicateStatus.pending_review
    resolved_action: Optional[ResolvedAction] = None
    resolved_at: Optional[datetime] = None


class DuplicateCandidateCreate(DuplicateCandidateBase):
    pass


class DuplicateCandidateOut(ORMModel, DuplicateCandidateBase):
    id: int
    created_at: datetime


# --- ReviewItem -----------------------------------------------------------
class ReviewItemBase(BaseModel):
    business_id: int
    transaction_id: Optional[int] = None
    issue_type: ReviewIssueType
    question: Optional[str] = None
    suggested_action: Optional[str] = None
    status: ReviewItemStatus = ReviewItemStatus.open
    resolved_at: Optional[datetime] = None


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
