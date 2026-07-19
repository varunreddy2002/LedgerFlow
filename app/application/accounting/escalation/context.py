"""Value objects passed along the escalation ladder.

The ladder threads a single mutable :class:`LadderContext` through its handlers;
each handler may attach an :class:`AccountProposal` or flag the row before passing
it on. Handlers return an immutable :class:`LadderOutcome` describing what finally
happened (auto-posted vs. parked for review).

The :class:`AccountClassifier` protocol is the seam for the (LLM) agent layer, kept
abstract so the deterministic handlers can be tested without any model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Protocol

from app.domain.enums import EscalationSource, NormalBalance
from app.application.accounting.repository import AccountRecord


@dataclass(frozen=True)
class AccountProposal:
    """A proposed counter-account for a bank row, from a rule or the agent.

    Carries *only* an account choice + confidence — never an amount. Money math is
    the builder's job; the classifier picks where, never how much.
    """

    account_code: str
    confidence: float
    source: EscalationSource
    reason_code: str


@dataclass
class LadderContext:
    """Mutable state for one bank row moving through the ladder."""

    bank_transaction_id: int
    business_id: int
    cash_account_id: int
    description: str
    amount: Decimal
    cash_movement: NormalBalance
    entry_date: date
    proposal: Optional[AccountProposal] = None
    large_amount: bool = False

    @property
    def fields(self) -> dict:
        """Field map for rule matching."""
        return {"description": self.description or ""}


@dataclass(frozen=True)
class LadderOutcome:
    """The terminal result of running the ladder on one bank row."""

    bank_transaction_id: int
    outcome: str                         # "posted" | "review"
    journal_entry_id: Optional[int] = None
    review_item_id: Optional[int] = None
    item_type: Optional[str] = None
    account_code: Optional[str] = None
    confidence: Optional[float] = None
    message: str = ""


class AccountClassifier(Protocol):
    """The agent seam: given a bank row and the posting-leaf accounts, propose a
    counter account (or None to defer). Implementations may call an LLM; they must
    never post or compute amounts."""

    def propose(
        self, context: LadderContext, leaves: List[AccountRecord]
    ) -> Optional[AccountProposal]:
        ...


class NullAccountClassifier:
    """A classifier that always defers (no agent configured). Keeps the chain shape
    constant so rows still flow Rule → Agent(no-op) → Review."""

    def propose(
        self, context: LadderContext, leaves: List[AccountRecord]
    ) -> Optional[AccountProposal]:
        return None
