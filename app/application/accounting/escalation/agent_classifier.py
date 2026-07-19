"""Bedrock-backed account classifier — the agent layer of the ladder.

Implements :class:`AccountClassifier` using a Claude model on Bedrock with structured
output. It is deliberately narrow: given a bank row and the *direction-valid* posting
leaves, it returns a single ``account_code`` + confidence + short reason. It never
sees or emits an amount — the money math is the builder's job.

Direction is enforced *before* the model sees the options: a money-in row is only
ever offered REVENUE leaves, a money-out row only EXPENSE leaves. So even a wrong
guess cannot violate cash-basis direction consistency.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import AccountType, EscalationSource, NormalBalance
from app.application.accounting.repository import AccountRecord
from app.application.accounting.escalation.context import AccountProposal, LadderContext

logger = get_logger(__name__)


class _AccountChoice(BaseModel):
    """Structured output schema for the classifier."""

    account_code: Optional[str] = Field(
        None, description="the chosen account code exactly as listed, or null if none fits"
    )
    confidence: float = Field(0.0, description="confidence 0.0-1.0 in the choice")
    reason: str = Field("", description="a short justification (<=12 words)")


_PROMPT = """You are a bookkeeping assistant for a small consulting business.
Classify this bank transaction to ONE general-ledger account from the list.

Transaction:
- description: {description}
- direction: {direction} ({movement})
- amount: (not shown — do not reason about the amount)

Candidate accounts (choose exactly one code, or null if none fit):
{options}

Rules:
- Pick the single best-fitting account code from the list above.
- If nothing fits, return null for account_code.
- Never invent a code that is not listed.
"""


class BedrockAccountClassifier:
    """Proposes a counter account for an unmatched bank row via Bedrock (Claude)."""

    def __init__(self, model: Optional[str] = None, region: Optional[str] = None) -> None:
        # Imported lazily so environments without langchain_aws/AWS can still import
        # the pipeline module and run the deterministic path.
        from langchain_aws import ChatBedrockConverse

        self._llm = ChatBedrockConverse(
            model=model or settings.default_chat_model,
            region_name=region or settings.aws_region,
            temperature=0,
        ).with_structured_output(_AccountChoice)

    def propose(
        self, context: LadderContext, leaves: List[AccountRecord]
    ) -> Optional[AccountProposal]:
        candidates = self._direction_valid(context.cash_movement, leaves)
        if not candidates:
            return None

        options = "\n".join(
            f"- {r.account_code}: {r.account_name}" for r in candidates
        )
        direction = "money in (deposit)" if context.cash_movement is NormalBalance.DEBIT else "money out (payment)"
        prompt = _PROMPT.format(
            description=context.description,
            direction=direction,
            movement=context.cash_movement.value,
            options=options,
        )

        choice: _AccountChoice = self._llm.invoke(prompt)
        valid_codes = {r.account_code for r in candidates}
        if not choice.account_code or choice.account_code not in valid_codes:
            logger.info("[agent_classifier] no valid choice for bank_txn=%s",
                        context.bank_transaction_id)
            return None

        return AccountProposal(
            account_code=choice.account_code,
            confidence=max(0.0, min(1.0, float(choice.confidence))),
            source=EscalationSource.AGENT,
            reason_code=f"agent:{choice.reason}"[:60],
        )

    @staticmethod
    def _direction_valid(
        movement: NormalBalance, leaves: List[AccountRecord]
    ) -> List[AccountRecord]:
        """Only offer revenue leaves for money-in, expense leaves for money-out."""
        wanted = AccountType.REVENUE if movement is NormalBalance.DEBIT else AccountType.EXPENSE
        return [r for r in leaves if r.account_type is wanted]


def default_classifier() -> BedrockAccountClassifier:
    """Construct the default Bedrock classifier (requires AWS Bedrock access)."""
    return BedrockAccountClassifier()
