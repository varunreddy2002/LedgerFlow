"""The deterministic classification layer — regex/keyword rules over source rows.

`AccountingRuleEngine` is pure and data-driven: it holds a list of :class:`RuleSpec`
(loaded from ``accounting_rules``) and returns the first matching rule by priority.
It never touches the database, so it is trivially unit-testable; :func:`load_rules`
is the thin adapter that reads rows into specs.

Match operators are dispatched from a registry (no ``if/elif`` ladder), so adding a
new operator is a one-line registration — Open/Closed in miniature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.models.ledger import AccountingRule

logger = get_logger(__name__)


@dataclass(frozen=True)
class RuleSpec:
    """A single compiled classification rule."""

    rule_id: Optional[int]
    rule_name: str
    match_field: str          # e.g. "description"
    op: str                   # "regex" | "contains" | "icontains" | "equals"
    value: str
    account_code: str
    confidence: float
    priority: int


@dataclass(frozen=True)
class RuleMatch:
    """The outcome of a successful rule evaluation."""

    account_code: str
    confidence: float
    rule_id: Optional[int]
    rule_name: str

    @property
    def reason_code(self) -> str:
        base = f"rule:{self.rule_id}" if self.rule_id is not None else "rule"
        return f"{base}:{self.rule_name}"[:60]


# ── match operators (registry / Strategy) ──────────────────────────────────
def _op_regex(field: str, value: str) -> bool:
    return re.search(value, field, re.IGNORECASE) is not None


def _op_contains(field: str, value: str) -> bool:
    return value in field


def _op_icontains(field: str, value: str) -> bool:
    return value.lower() in field.lower()


def _op_equals(field: str, value: str) -> bool:
    return field.strip().lower() == value.strip().lower()


_OPERATORS: Dict[str, Callable[[str, str], bool]] = {
    "regex": _op_regex,
    "contains": _op_contains,
    "icontains": _op_icontains,
    "equals": _op_equals,
}


class AccountingRuleEngine:
    """Evaluates a source row's fields against ordered rules; first match wins."""

    def __init__(self, rules: List[RuleSpec]) -> None:
        # Stable priority order (lower runs first); ties broken by rule_id.
        self._rules = sorted(rules, key=lambda r: (r.priority, r.rule_id or 0))

    def match(self, fields: Dict[str, str]) -> Optional[RuleMatch]:
        """Return the first rule whose condition holds for ``fields``, or None.

        ``fields`` maps ``match_field`` names (e.g. ``"description"``) to their text.
        An unknown operator is skipped with a warning rather than crashing a batch.
        """
        for rule in self._rules:
            field_value = fields.get(rule.match_field)
            if field_value is None:
                continue
            op = _OPERATORS.get(rule.op)
            if op is None:
                logger.warning("[rule_engine] unknown operator %r on rule %s",
                               rule.op, rule.rule_name)
                continue
            if op(field_value, rule.value):
                logger.info("[rule_engine] matched rule=%r -> account=%s conf=%.2f",
                            rule.rule_name, rule.account_code, rule.confidence)
                return RuleMatch(
                    account_code=rule.account_code,
                    confidence=rule.confidence,
                    rule_id=rule.rule_id,
                    rule_name=rule.rule_name,
                )
        return None


def load_rules(session: Session, business_id: int) -> List[RuleSpec]:
    """Load a business's active accounting rules into :class:`RuleSpec` objects."""
    rows = (
        session.query(AccountingRule)
        .filter(
            AccountingRule.business_id == business_id,
            AccountingRule.is_active.is_(True),
        )
        .order_by(AccountingRule.priority)
        .all()
    )
    specs: List[RuleSpec] = []
    for r in rows:
        conditions = r.conditions or {}
        actions = r.actions or {}
        account_code = actions.get("account_code")
        if account_code is None:
            logger.warning("[rule_engine] rule %s has no account_code action; skipping", r.id)
            continue
        specs.append(RuleSpec(
            rule_id=r.id,
            rule_name=r.rule_name,
            match_field=conditions.get("match_field", "description"),
            op=conditions.get("op", "regex"),
            value=conditions.get("value", ""),
            account_code=account_code,
            confidence=float(actions.get("confidence", 0.0)),
            priority=r.priority,
        ))
    return specs
