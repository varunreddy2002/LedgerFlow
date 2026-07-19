"""Typed inputs/outputs for the review queue (DTOs across the boundary)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.enums import ApprovalDecision, EscalationSource, ReviewItemType, ReviewStatus
from app.domain.models.ledger import ReviewItem


@dataclass(frozen=True)
class ReviewResolution:
    """A human decision on a review item.

    ``account_code`` overrides the proposed account (a correction → the flywheel).
    ``create_rule`` controls whether a learned rule is written on a successful post.
    """

    decision: ApprovalDecision
    account_code: Optional[str] = None
    notes: Optional[str] = None
    actor: str = "system"
    create_rule: bool = True


@dataclass(frozen=True)
class ResolutionResult:
    """The outcome of resolving a review item."""

    review_item_id: int
    status: str                              # "resolved" | "dismissed"
    journal_entry_id: Optional[int] = None
    account_code: Optional[str] = None
    rule_created: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "review_item_id": self.review_item_id,
            "status": self.status,
            "journal_entry_id": self.journal_entry_id,
            "account_code": self.account_code,
            "rule_created": self.rule_created,
            "message": self.message,
        }


@dataclass(frozen=True)
class ReviewItemView:
    """A read model of a review item for listing (chat / API)."""

    id: int
    item_type: ReviewItemType
    status: ReviewStatus
    subject_type: str
    subject_id: int
    source: EscalationSource
    confidence: Optional[float]
    proposed_account_code: Optional[str]
    proposed_resolution: Optional[dict]
    description: Optional[str] = None
    amount: Optional[str] = None

    @classmethod
    def from_model(cls, item: ReviewItem, *, description=None, amount=None) -> "ReviewItemView":
        proposed = item.proposed_resolution or {}
        return cls(
            id=item.id,
            item_type=item.item_type,
            status=item.status,
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            source=item.source,
            confidence=item.confidence,
            proposed_account_code=proposed.get("account_code"),
            proposed_resolution=item.proposed_resolution,
            description=description,
            amount=amount,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "item_type": self.item_type.value,
            "status": self.status.value,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "source": self.source.value,
            "confidence": self.confidence,
            "proposed_account_code": self.proposed_account_code,
            "description": self.description,
            "amount": self.amount,
        }
