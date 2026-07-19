"""The learning flywheel — turn a human correction into a new accounting rule.

When a person resolves a review item by choosing an account, `RuleLearner` writes a
non-system :class:`AccountingRule` so the *deterministic* layer handles the same
vendor automatically next time. This is memory type 2 (learned accounting memory):
auditable — you can point at exactly why the system remembers a mapping.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.models.ledger import AccountingRule

logger = get_logger(__name__)

# Learned rules run before seeded ones (lower priority number = earlier).
_LEARNED_PRIORITY = 5
_LEARNED_CONFIDENCE = 0.90


class RuleLearner:
    """Creates learned classification rules from resolved review items."""

    def __init__(self, session: Session, business_id: int) -> None:
        self._session = session
        self._business_id = business_id

    def learn(
        self, description: Optional[str], account_code: str,
        confidence: float = _LEARNED_CONFIDENCE,
    ) -> bool:
        """Create a learned rule mapping ``description`` → ``account_code``.

        Returns True if a rule was created, False if the input was too weak to key on
        or an equivalent learned rule already exists (idempotent flywheel).
        """
        value = self._keyword(description)
        if not value:
            logger.info("[rule_learning] no usable keyword in %r; not learning", description)
            return False

        if self._exists(value, account_code):
            logger.info("[rule_learning] rule for %r -> %s already exists", value, account_code)
            return False

        self._session.add(AccountingRule(
            business_id=self._business_id,
            rule_name=f"Learned: {value[:60]} -> {account_code}",
            rule_type="description",
            conditions={"match_field": "description", "op": "icontains", "value": value},
            actions={"account_code": account_code, "confidence": confidence},
            priority=_LEARNED_PRIORITY,
            is_system=False,
            is_active=True,
        ))
        self._session.flush()
        logger.info("[rule_learning] learned %r -> %s (conf=%.2f)", value, account_code, confidence)
        return True

    @staticmethod
    def _keyword(description: Optional[str]) -> Optional[str]:
        """Derive a stable match key from a bank description.

        Uses the leading alphabetic tokens (the vendor name) so amounts, dates and
        reference numbers don't make the rule too specific to re-fire.
        """
        if not description:
            return None
        cleaned = description.strip().lower()
        tokens = re.findall(r"[a-z][a-z&.\-']*", cleaned)
        if not tokens:
            return None
        return " ".join(tokens[:3]).strip()

    def _exists(self, value: str, account_code: str) -> bool:
        for rule in (
            self._session.query(AccountingRule)
            .filter(
                AccountingRule.business_id == self._business_id,
                AccountingRule.is_system.is_(False),
            )
        ):
            conditions = rule.conditions or {}
            actions = rule.actions or {}
            if conditions.get("value") == value and actions.get("account_code") == account_code:
                return True
        return False
