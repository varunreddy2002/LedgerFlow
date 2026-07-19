"""Unit tests for AccountingRuleEngine — matching, priority, operators."""

from __future__ import annotations

from app.application.accounting.rule_engine import AccountingRuleEngine, RuleSpec


def _engine(*specs):
    return AccountingRuleEngine(list(specs))


def test_regex_match_is_case_insensitive():
    engine = _engine(RuleSpec(1, "cloud", "description", "regex", r"aws", "5320", 0.9, 10))
    match = engine.match({"description": "Monthly AWS invoice"})
    assert match is not None and match.account_code == "5320"


def test_first_match_by_priority_wins():
    engine = _engine(
        RuleSpec(1, "specific", "description", "regex", r"aws lambda", "5330", 0.9, 5),
        RuleSpec(2, "general", "description", "regex", r"aws", "5320", 0.8, 10),
    )
    match = engine.match({"description": "aws lambda usage"})
    assert match.account_code == "5330"  # lower priority number runs first


def test_no_match_returns_none():
    engine = _engine(RuleSpec(1, "cloud", "description", "regex", r"aws", "5320", 0.9, 10))
    assert engine.match({"description": "grocery store"}) is None


def test_contains_and_equals_operators():
    engine = _engine(
        RuleSpec(1, "contains", "description", "contains", "Gusto", "5110", 0.85, 10),
        RuleSpec(2, "equals", "description", "equals", "wire fee", "5810", 0.85, 20),
    )
    assert engine.match({"description": "Gusto payroll"}).account_code == "5110"
    assert engine.match({"description": "WIRE FEE"}).account_code == "5810"


def test_unknown_operator_is_skipped_not_fatal():
    engine = _engine(
        RuleSpec(1, "bad", "description", "nonsense_op", "x", "5320", 0.9, 5),
        RuleSpec(2, "good", "description", "regex", r"aws", "5330", 0.9, 10),
    )
    match = engine.match({"description": "aws bill"})
    assert match.account_code == "5330"


def test_missing_field_is_skipped():
    engine = _engine(RuleSpec(1, "vendor", "vendor_name", "regex", r"aws", "5320", 0.9, 10))
    assert engine.match({"description": "aws"}) is None  # no vendor_name field


def test_reason_code_is_bounded_and_descriptive():
    engine = _engine(RuleSpec(7, "Cloud hosting", "description", "regex", r"aws", "5330", 0.9, 10))
    match = engine.match({"description": "aws"})
    assert match.reason_code.startswith("rule:7:")
    assert len(match.reason_code) <= 60
