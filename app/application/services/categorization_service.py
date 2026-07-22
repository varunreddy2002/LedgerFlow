"""Categorization: turns raw BankTransaction rows into balanced double-entry
Transactions, in two passes.

This is the accounting-judgment layer ingestion deliberately stays out of —
picking *which account* a bank row belongs to, and writing the two-sided
entry that keeps the ledger balanced.

    1. Pull every bank_transactions row in status=NEW (`categorize_bank_transactions`).
    2. Rule pass: match each row's normalized_description against active
       accounting_rules, first match by priority wins (`_match_rule`). A
       match posts a Transaction right away, status APPROVED or
       REVIEW_REQUIRED depending on the rule's own confidence.
    3. AI fallback (`_run_ai_fallback`): whatever the rules left unmatched
       goes through the AI suggester in small batches
       (`settings.categorization_ai_batch_size` at a time, sequential calls —
       not one call per row) instead of being abandoned. A suggestion is
       NEVER auto-approved — every AI-sourced Transaction is forced
       REVIEW_REQUIRED, with the model's reasoning written to
       `review_notes` so a human reviewer has context instead of a blank row.
    4. Both builders share `_build_transaction` for the actual double-entry
       construction — one entry for the bank's own cash account, one for the
       matched account. The debit/credit split follows the bank row's
       CashDirection only; see that function's docstring for why.
    5. A bank row that neither a rule nor the AI could place stays
       REVIEW_REQUIRED with nothing posted — same floor as before the AI
       fallback existed, it just now takes two shots instead of one.
    6. One AuditEvent (actor=RULE_ENGINE) summarizes the whole batch —
       counting rule matches and AI suggestions separately.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import re

from app.application.agents import suggest_accounts
from app.domain.models import Account, AccountingRule, AuditEvent, BankTransaction, Transaction, TransactionEntry
from app.domain.enums import (
    AuditActorType, AuditEventType, BankTxnStatus, CashDirection, RuleStatus, TransactionStatus,
)
from app.domain.schemas import CategorizationResult
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def categorize_bank_transactions(db, business_id: int, document_id: Optional[int] = None) -> None:
    """Match NEW bank_transactions against accounting_rules, then run
    whatever's left through the AI fallback. Scoped to one document's rows
    when called right after CSV ingestion; scans the business's whole NEW
    backlog when document_id is omitted (e.g. a future manual re-run).
    """
    query = db.query(BankTransaction).filter(
        BankTransaction.business_id == business_id,
        BankTransaction.status == BankTxnStatus.NEW,
    )
    if document_id is not None:
        query = query.filter(BankTransaction.document_id == document_id)
    bank_transactions = query.all()
    if not bank_transactions:
        return

    rules = _load_active_rules(db, business_id)
    account_by_code = {a.account_code: a for a in _load_accounts(db, business_id)}

    rule_matched = 0
    unmatched: List[BankTransaction] = []
    for bank_txn in bank_transactions:
        match = _match_rule(bank_txn.normalized_description or "", rules)
        if match is None:
            unmatched.append(bank_txn)
            continue

        rule, account_code, confidence = match
        account = account_by_code.get(account_code)
        if account is None:
            # Rules are user-editable JSON, not a fixed schema — a rule
            # pointing at a stale/typo'd account_code is a config bug, not a
            # "the AI might know better" case, so it goes straight to
            # REVIEW_REQUIRED rather than into the AI fallback batch.
            logger.warning(
                "Rule %r targets unknown account_code=%s for business_id=%s: bank_transaction_id=%s -> REVIEW_REQUIRED",
                rule.rule_name, account_code, business_id, bank_txn.id,
            )
            bank_txn.status = BankTxnStatus.REVIEW_REQUIRED
            continue

        status = (
            TransactionStatus.APPROVED
            if confidence >= settings.categorization_confidence_threshold
            else TransactionStatus.REVIEW_REQUIRED
        )
        db.add(_build_transaction(
            bank_txn, account_id=account.id, name=rule.rule_name, status=status,
            confidence=confidence, review_notes=None, created_by="accounting_rules",
        ))
        bank_txn.status = BankTxnStatus.PROCESSED
        rule_matched += 1

    ai_suggested = _run_ai_fallback(db, unmatched, account_by_code)
    review_required = len(unmatched) - ai_suggested

    _record_audit_event(
        db, business_id=business_id, document_id=document_id,
        result=CategorizationResult(
            rule_matched=rule_matched,
            ai_suggested=ai_suggested,
            review_required=review_required,
            total_bank_transactions=len(bank_transactions),
        ),
    )
    logger.info(
        "Categorization finished: business_id=%s document_id=%s rule_matched=%d ai_suggested=%d review_required=%d",
        business_id, document_id, rule_matched, ai_suggested, review_required,
    )


def _load_active_rules(db, business_id: int) -> List[AccountingRule]:
    return (
        db.query(AccountingRule)
        .filter(AccountingRule.business_id == business_id, AccountingRule.status == RuleStatus.ACTIVE)
        .order_by(AccountingRule.priority.asc())
        .all()
    )


def _load_accounts(db, business_id: int) -> List[Account]:
    return db.query(Account).filter(Account.business_id == business_id).all()


def _match_rule(text: str, rules: List[AccountingRule]) -> Optional[Tuple[AccountingRule, str, float]]:
    """First rule (priority ascending) whose regex matches the given
    normalized text. Only the seeded conditions shape
    (field=normalized_description, operator=regex) is understood today — the
    JSON leaves room for other match strategies later without a migration.
    Takes plain text rather than a BankTransaction so reconciliation_service
    can reuse this same matcher against invoice/bill line descriptions."""
    for rule in rules:
        condition = rule.conditions
        if condition.get("field") != "normalized_description" or condition.get("operator") != "regex":
            continue
        pattern = condition.get("value")
        if pattern and re.search(pattern, text, re.IGNORECASE):
            account_code = rule.actions.get("account_code")
            confidence = rule.actions.get("confidence", 0.0)
            if account_code:
                return rule, account_code, confidence
    return None


def _run_ai_fallback(db, unmatched: List[BankTransaction], account_by_code: Dict[str, Account]) -> int:
    """Batch whatever the rule engine couldn't match through the AI
    suggester, `settings.categorization_ai_batch_size` rows per call
    (sequential, not parallel — the whole point is staying easy on rate
    limits, not raw throughput). Every resulting Transaction is forced
    REVIEW_REQUIRED regardless of anything the model says — a suggestion
    here has no track record the way a curated rule confidence does.

    Returns the number of Transactions created (i.e. rows the AI placed).
    Rows the AI also can't place — including a whole batch failing outright
    (network/parsing error) — stay REVIEW_REQUIRED with nothing posted,
    same floor as before this fallback existed.
    """
    if not unmatched:
        return 0

    postable_accounts = [
        {"account_code": a.account_code, "account_name": a.account_name}
        for a in account_by_code.values() if a.posting_allowed
    ]
    created_by = f"ai_agent:{settings.default_chat_model}"

    batch_size = settings.categorization_ai_batch_size
    created = 0
    for i in range(0, len(unmatched), batch_size):
        batch = unmatched[i:i + batch_size]
        rows = [
            {
                "row_id": bt.id,
                "description": bt.description,
                "amount": str(bt.amount),
                "direction": bt.direction.value,
            }
            for bt in batch
        ]

        try:
            result = suggest_accounts(rows, postable_accounts)
        except Exception:
            logger.exception(
                "AI categorization batch failed for %d bank_transactions, leaving REVIEW_REQUIRED",
                len(batch),
            )
            for bt in batch:
                bt.status = BankTxnStatus.REVIEW_REQUIRED
            continue

        suggestion_by_row_id = {s.row_id: s for s in result.suggestions}
        for bt in batch:
            suggestion = suggestion_by_row_id.get(bt.id)
            account = (
                account_by_code.get(suggestion.account_code)
                if suggestion and suggestion.account_code else None
            )
            if account is None:
                bt.status = BankTxnStatus.REVIEW_REQUIRED
                continue

            db.add(_build_transaction(
                bt, account_id=account.id, name=f"AI-suggested: {account.account_name}",
                status=TransactionStatus.REVIEW_REQUIRED, confidence=None,
                review_notes=suggestion.reasoning, created_by=created_by,
            ))
            bt.status = BankTxnStatus.PROCESSED
            created += 1

    return created


def _build_transaction(
    bank_txn: BankTransaction, *, account_id: int, name: str, status: TransactionStatus,
    confidence: Optional[float], review_notes: Optional[str], created_by: str,
) -> Transaction:
    """Build a balanced Transaction: one entry for the bank's own cash
    account, one for the matched account. The debit/credit split follows the
    bank row's CashDirection only, not either account's normal_balance:

        INFLOW  -> Dr Cash (+amount)          / Cr matched account (-amount)
        OUTFLOW -> Dr matched account (+amount) / Cr Cash (-amount)

    This holds regardless of what the matched account is (revenue, expense,
    liability paydown, owner draw...) — normal_balance only describes which
    side increases an account's balance for reporting, it doesn't change how
    a two-line entry is built from a single cash movement. Shared by both the
    rule-match and AI-fallback paths — only naming/status/confidence/notes
    differ between them.
    """
    amount = bank_txn.amount
    if bank_txn.direction == CashDirection.INFLOW:
        cash_amount, matched_amount = amount, -amount
    else:
        cash_amount, matched_amount = -amount, amount

    transaction = Transaction(
        business_id=bank_txn.business_id,
        bank_transaction_id=bank_txn.id,
        transaction_date=bank_txn.transaction_date,
        name=name,
        description=bank_txn.description,
        status=status,
        confidence_score=confidence,
        review_notes=review_notes,
        created_by=created_by,
    )
    transaction.entries = [
        TransactionEntry(account_id=bank_txn.account_id, amount=cash_amount, description=bank_txn.description, created_by=created_by),
        TransactionEntry(account_id=account_id, amount=matched_amount, description=bank_txn.description, created_by=created_by),
    ]
    return transaction


def _record_audit_event(db, *, business_id: int, document_id: Optional[int], result: CategorizationResult) -> None:
    """Append an audit-trail row summarizing one categorization batch.
    Keyed to the document when this ran right after ingestion; keyed to the
    business itself for a standalone/whole-backlog run (no single document
    caused it)."""
    entity_type, entity_id = ("document", document_id) if document_id is not None else ("business", business_id)
    db.add(AuditEvent(
        business_id=business_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=AuditEventType.CLASSIFIED,
        actor_type=AuditActorType.RULE_ENGINE,
        new_values=result.model_dump(),
    ))
