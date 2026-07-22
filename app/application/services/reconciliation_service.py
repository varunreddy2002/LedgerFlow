"""Reconciliation: before any generic keyword/AI categorization runs, check
whether a NEW bank_transaction is actually a payment against an already-known
Invoice/Bill. A match here is much stronger evidence than a keyword rule —
it's an existing paper trail, not an inference from bank text alone.

    1. `reconcile(db, business_id)` — entry point, called first from both the
       CSV and PDF ingestion pipelines (order of upload doesn't matter —
       whichever side arrives second triggers the match).
    2. Candidates are deliberately narrow: only bank_transactions still NEW,
       only Invoice/Bill still DRAFT. REVIEW_REQUIRED ones are excluded on
       purpose — that status means the party (vendor/customer) never
       resolved, and auto-marking such an invoice PAID would finalize it
       without ever knowing who actually paid, undermining the whole point
       of flagging it for review in the first place.
    3. Match key: exact amount (sum of line quantity*unit_price + tax).
       Ties broken by the document's invoice/bill number, or its resolved
       party's name, appearing in the bank description — plain substring
       match, no fuzzy matching, same style as the rest of ingestion. Still
       ambiguous, or zero candidates -> leave the bank row NEW; it falls
       through to the normal rule/AI categorization pass unchanged.
    4. On a match, resolve an account per line by reusing the exact same
       rule engine + AI fallback `categorize_bank_transactions` already
       uses (`_match_rule`, `suggest_accounts`) — a line description like
       "Consulting retainer" is matched the same way a bank description is.
       Any line that can't get an account aborts that reconciliation
       entirely: the bank row stays NEW, the document stays untouched,
       nothing partial gets posted.
    5. Posts one balanced Transaction: Dr Cash / Cr each line's account for
       an invoice (money in), Cr Cash / Dr each line's account for a bill
       (money out) — same CashDirection-driven convention as
       categorization_service.py, just with one cash entry against
       potentially several line entries instead of always exactly two.
       status = APPROVED only if every line resolved via a rule (no AI
       involved); REVIEW_REQUIRED if any line needed the AI fallback.

Known, accepted limitation (not a bug, see project memory): only NEW/DRAFT
rows are ever candidates. Once a bank row is PROCESSED or an invoice stays
REVIEW_REQUIRED, nothing here retroactively reconciles it later — that would
mean editing an already-posted (immutable) Transaction, or auto-resolving a
party ingestion deliberately declined to guess at. Both are real features,
not this one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Union
import re

from app.application.agents import suggest_accounts
from app.application.services.categorization_service import _load_accounts, _load_active_rules, _match_rule
from app.domain.models import (
    Account, AccountingRule, AuditEvent, BankTransaction, Bill, Invoice, Transaction, TransactionEntry,
)
from app.domain.enums import (
    AuditActorType, AuditEventType, BankTxnStatus, CashDirection, InvoiceBillStatus, TransactionStatus,
)
from app.domain.schemas import ReconciliationResult
from app.core.logging import get_logger

logger = get_logger(__name__)

_Document = Union[Invoice, Bill]


def reconcile(db, business_id: int) -> int:
    """Match NEW bank_transactions against DRAFT invoices/bills. Returns the
    number reconciled. Call this before categorize_bank_transactions — a
    reconciled bank_transaction never reaches the generic rule/AI pass."""
    bank_txns = (
        db.query(BankTransaction)
        .filter(BankTransaction.business_id == business_id, BankTransaction.status == BankTxnStatus.NEW)
        .all()
    )
    if not bank_txns:
        return 0

    open_invoices = (
        db.query(Invoice)
        .filter(Invoice.business_id == business_id, Invoice.status == InvoiceBillStatus.DRAFT)
        .all()
    )
    open_bills = (
        db.query(Bill)
        .filter(Bill.business_id == business_id, Bill.status == InvoiceBillStatus.DRAFT)
        .all()
    )
    if not open_invoices and not open_bills:
        return 0

    rules = _load_active_rules(db, business_id)
    account_by_code = {a.account_code: a for a in _load_accounts(db, business_id)}

    reconciled = 0
    for bank_txn in bank_txns:
        pool = open_invoices if bank_txn.direction == CashDirection.INFLOW else open_bills
        match = _find_match(bank_txn, pool)
        if match is None:
            continue

        if _post_reconciliation(db, bank_txn, match, rules, account_by_code):
            pool.remove(match)  # this doc is claimed, don't match it again this pass
            reconciled += 1

    if reconciled:
        _record_audit_event(db, business_id, ReconciliationResult(
            reconciled_count=reconciled, bank_transactions_scanned=len(bank_txns),
        ))
        logger.info(
            "Reconciliation finished: business_id=%s reconciled=%d/%d",
            business_id, reconciled, len(bank_txns),
        )
    return reconciled


def _find_match(bank_txn: BankTransaction, pool: List[_Document]) -> Optional[_Document]:
    """Exact-amount match; ties broken by the document's number or its
    resolved party's name appearing in the bank description."""
    candidates = [doc for doc in pool if _document_total(doc) == bank_txn.amount]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) < 1:
        return None

    description = _normalize(bank_txn.description or "")
    narrowed = [
        doc for doc in candidates
        if (_document_number(doc) and _normalize(_document_number(doc)) in description)
        or (_party_name(doc) and _normalize(_party_name(doc)) in description)
    ]
    return narrowed[0] if len(narrowed) == 1 else None


def _post_reconciliation(
    db, bank_txn: BankTransaction, doc: _Document, rules: List[AccountingRule],
    account_by_code: Dict[str, Account],
) -> bool:
    """Resolve an account per line (rule engine, then AI fallback), and post
    one balanced Transaction. Any line that can't get an account aborts the
    whole match — nothing partial gets posted."""
    is_invoice = isinstance(doc, Invoice)

    resolved: List[tuple] = []  # (line, Account)
    unresolved = []
    for line in doc.lines:
        match = _match_rule(_normalize(line.description or ""), rules)
        account = account_by_code.get(match[1]) if match else None
        if account:
            resolved.append((line, account))
        else:
            unresolved.append(line)

    used_ai = bool(unresolved)
    if unresolved:
        rows = [
            {
                "row_id": line.id,
                "description": line.description,
                "amount": str((line.quantity * line.unit_price).quantize(Decimal("0.01"))),
                "direction": "inflow" if is_invoice else "outflow",
            }
            for line in unresolved
        ]
        postable_accounts = [
            {"account_code": a.account_code, "account_name": a.account_name}
            for a in account_by_code.values() if a.posting_allowed
        ]
        try:
            result = suggest_accounts(rows, postable_accounts)
        except Exception:
            logger.exception(
                "AI line-account suggestion failed reconciling %s id=%s, leaving unreconciled",
                "Invoice" if is_invoice else "Bill", doc.id,
            )
            return False

        suggestion_by_row_id = {s.row_id: s for s in result.suggestions}
        for line in unresolved:
            suggestion = suggestion_by_row_id.get(line.id)
            account = account_by_code.get(suggestion.account_code) if suggestion and suggestion.account_code else None
            if account is None:
                return False  # any unresolved line aborts the whole match
            resolved.append((line, account))

    entries = []
    line_account_field = "revenue_account_id" if is_invoice else "expense_account_id"
    for line, account in resolved:
        line_amount = (line.quantity * line.unit_price + line.tax_amount).quantize(Decimal("0.01"))
        setattr(line, line_account_field, account.id)
        entries.append(TransactionEntry(
            account_id=account.id,
            amount=-line_amount if is_invoice else line_amount,
            description=line.description,
            created_by="reconciliation",
        ))
    entries.append(TransactionEntry(
        account_id=bank_txn.account_id,
        amount=bank_txn.amount if is_invoice else -bank_txn.amount,
        description=bank_txn.description,
        created_by="reconciliation",
    ))

    status = TransactionStatus.REVIEW_REQUIRED if used_ai else TransactionStatus.APPROVED
    doc_number = _document_number(doc) or str(doc.id)
    transaction = Transaction(
        business_id=bank_txn.business_id,
        bank_transaction_id=bank_txn.id,
        transaction_date=bank_txn.transaction_date,
        name=f"{'Invoice' if is_invoice else 'Bill'} payment: {doc_number}",
        description=bank_txn.description,
        status=status,
        created_by="reconciliation",
    )
    transaction.entries = entries
    db.add(transaction)
    db.flush()  # need transaction.id for doc.accounting_transaction_id below

    doc.bank_transaction_id = bank_txn.id
    doc.accounting_transaction_id = transaction.id
    doc.status = InvoiceBillStatus.PAID
    bank_txn.status = BankTxnStatus.PROCESSED
    return True


def _document_total(doc: _Document) -> Decimal:
    return sum(
        (line.quantity * line.unit_price + line.tax_amount for line in doc.lines),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def _document_number(doc: _Document) -> Optional[str]:
    return doc.invoice_number if isinstance(doc, Invoice) else doc.bill_number


def _party_name(doc: _Document) -> Optional[str]:
    if isinstance(doc, Invoice):
        return doc.customer.customer_name if doc.customer else None
    return doc.vendor.vendor_name if doc.vendor else None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _record_audit_event(db, business_id: int, result: ReconciliationResult) -> None:
    db.add(AuditEvent(
        business_id=business_id,
        entity_type="business",
        entity_id=business_id,
        event_type=AuditEventType.RECONCILED,
        actor_type=AuditActorType.SYSTEM,
        new_values=result.model_dump(),
    ))
