"""Document ingestion: turns an uploaded file into DB rows.

Pure capture layer — a CSV row becomes a `BankTransaction`, a PDF becomes an
`Invoice` (we're the seller) or a `Bill` (we're the buyer), each with lines.
No accounting judgment happens here: no account is picked for *what* the
money was spent on, no `Transaction`/`TransactionEntry` is written. That's
the categorization layer's job, run separately and later.

CSV pipeline, step by step (see `_process_csv`):
    1. Resolve which CSV column is which (`_resolve_column_mapping`).
    2. Resolve the bank/cash account this statement posts against
       (`_resolve_bank_account`).
    3. Parse every row into a plain dict (`_parse_csv_rows`).
    4. Fingerprint-dedupe and build `BankTransaction` rows (`_build_bank_transactions`).
    5. Persist rows + a `DocumentExtraction` audit copy of the column mapping
       + an `AuditEvent` summarizing the outcome, then mark the document PROCESSED.

PDF pipeline, step by step (see `_process_pdf`):
    1. OCR-extract seller/buyer/dates/line items (`extract_document`).
    2. Classify invoice vs. bill from which party matches the business
       (`_classify_pdf`) — exact normalized-name match only, for now.
    3. Resolve the counterparty against existing Vendors/Customers by name
       (`_resolve_party`) — does NOT auto-create an unmatched party.
    4. Dedupe against an existing Invoice/Bill with the same party + invoice
       number (`_find_duplicate`).
    5. Build the Invoice/Bill header + lines. Status is REVIEW_REQUIRED
       instead of DRAFT when the party didn't resolve or there are no line
       items — that row still gets created, just flagged for a human before
       it can be reconciled against a payment.
    6. Persist + a `DocumentExtraction` audit copy of the raw extraction +
       an `AuditEvent` summarizing the outcome, then mark the document PROCESSED.

Both pipelines mark the document FAILED (with an AuditEvent explaining why)
whenever they hit something they can't recover from at all — an incomplete
CSV mapping, a PDF that can't be classified as invoice-vs-bill, or a missing
required date. FAILED means "couldn't produce a row"; REVIEW_REQUIRED (on the
row itself, not the document) means "produced a row, but don't trust it yet."
"""

from pathlib import Path
from typing import Optional
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from app.application.agents import extract_document, map_columns
from app.application.services.categorization_service import categorize_bank_transactions
from app.application.services.reconciliation_service import reconcile
from app.core.config import settings
from app.infrastructure.db import session_scope
from app.domain.models import (
    Account, AuditEvent, BankTransaction, Bill, BillLine, Business, Customer,
    Document, DocumentExtraction, Invoice, InvoiceLine, Vendor,
)
from app.domain.enums import (
    AuditActorType, AuditEventType, CashDirection, DocumentStatus, InvoiceBillStatus, SourceType,
)
from app.domain.schemas import CSVColumnMapping, CsvIngestionResult, PdfIngestionResult
from app.core.logging import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent.parent
UPLOAD_DIR = ROOT_DIR / "uploads"

# Bank/cash leaf every ingested CSV statement posts against, per business.
# Picking which account per-upload is future work (multi-account businesses).
DEFAULT_BANK_ACCOUNT_CODE = "1110"

# extraction_type recorded on DocumentExtraction. Deliberately not reusing
# SourceType — that enum classifies the *document*, these strings classify
# the *kind of extraction* that produced the JSON payload.
CSV_EXTRACTION_TYPE = "csv_bank_statement"
PDF_EXTRACTION_TYPE = {
    SourceType.INVOICE: "pdf_invoice",
    SourceType.VENDOR_BILL: "pdf_bill",
}

# Canonical CSV header -> CSVColumnMapping field, with the description text
# handed to the LLM mapper when headers don't already match this shape.
# NOTE: most bank CSVs only give ONE date column, and it's the posted/cleared
# date, not a separate transaction date — both fields describe that same column.
REQUIRED_COLUMNS = {
    "date": "the date the transaction posted or cleared on the bank statement",
    "description": "the narration or merchant name or transaction description",
    "amount": "the transaction amount, can be negative for debits",
}


def run_ingestion(business_id: int, filename: str, content: bytes, ext: str) -> None:
    """Entry point for the upload background task: store the file, create the
    Document row, then dispatch to the CSV or PDF pipeline."""
    logger.info("Ingestion started: business_id=%s filename=%s ext=%s", business_id, filename, ext)

    file_path = UPLOAD_DIR / str(business_id) / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)

    with session_scope() as db:
        doc = Document(
            business_id=business_id,
            filename=filename,
            file_path=str(file_path),
            source=SourceType.BANK_STATEMENT if ext == ".csv" else SourceType.UNKNOWN,
            status=DocumentStatus.UPLOADED,
            sha256_checksum=_checksum(content),
        )
        db.add(doc)
        db.flush()  # assign doc.id before it's referenced by child rows
        logger.info("Document row created: document_id=%s status=%s", doc.id, doc.status)

        doc.status = DocumentStatus.PROCESSING
        if ext == ".csv":
            _process_csv(db, business_id, doc)
        else:
            _process_pdf(db, business_id, doc)

        logger.info("Ingestion finished: document_id=%s final_status=%s", doc.id, doc.status)


# ─────────────────────────────────────────────────────────────────────────
# CSV pipeline
# ─────────────────────────────────────────────────────────────────────────

def _process_csv(db, business_id: int, doc: Document) -> None:
    """CSV -> BankTransaction rows. Mutates `doc.status` in place; every exit
    path (success or failure) also leaves an AuditEvent explaining why."""
    df = pd.read_csv(doc.file_path)

    mapping = _resolve_column_mapping(db, doc, df)
    if mapping is None:
        return  # already marked FAILED + audited inside _resolve_column_mapping

    account_id = _resolve_bank_account(db, business_id)
    if account_id is None:
        logger.error(
            "Default bank account %s not found for business_id=%s (run /setup?): document_id=%s -> FAILED",
            DEFAULT_BANK_ACCOUNT_CODE, business_id, doc.id,
        )
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            reason=f"Default bank account '{DEFAULT_BANK_ACCOUNT_CODE}' not found for this business.",
        )
        return

    parsed_rows = _parse_csv_rows(df, mapping)
    bank_transactions, duplicate_count = _build_bank_transactions(
        db, business_id=business_id, account_id=account_id, document_id=doc.id, parsed_rows=parsed_rows,
    )

    db.add_all(bank_transactions)
    db.add(DocumentExtraction(
        document_id=doc.id,
        extraction_type=CSV_EXTRACTION_TYPE,
        extracted_json=mapping,
    ))
    _record_audit_event(
        db, business_id=business_id, document_id=doc.id,
        event_type=AuditEventType.EXTRACTED,
        new_values=CsvIngestionResult(
            bank_transactions_created=len(bank_transactions),
            duplicates_skipped=duplicate_count,
            total_rows=len(parsed_rows),
        ).model_dump(),
    )

    # Flush so the new bank_transactions have ids and are visible to
    # reconcile()/categorize_bank_transactions's own queries (this session
    # has autoflush=False, so those queries wouldn't otherwise see them yet).
    db.flush()
    # Reconciliation runs first — a bank row that's actually paying a known
    # invoice/bill is stronger evidence than any keyword rule, and shouldn't
    # be claimed by the generic categorizer before reconciliation gets a look.
    reconcile(db, business_id)
    # Flush again: reconcile() flips reconciled rows to PROCESSED in memory,
    # but categorize_bank_transactions runs its own fresh "status == NEW"
    # query next — without this, autoflush=False means it wouldn't see that
    # update yet and would reprocess an already-reconciled row a second time.
    db.flush()
    categorize_bank_transactions(db, business_id=business_id, document_id=doc.id)

    doc.status = DocumentStatus.PROCESSED
    doc.processed_at = datetime.now()
    logger.info(
        "CSV processed: document_id=%s imported=%d duplicates_skipped=%d total_rows=%d",
        doc.id, len(bank_transactions), duplicate_count, len(parsed_rows),
    )


def _resolve_column_mapping(db, doc: Document, df: pd.DataFrame) -> Optional[dict]:
    """Figure out which CSV column is which canonical field.

    Tries an exact header match first (cheap, no LLM call); falls back to the
    LLM-based column mapper when headers don't already match our shape.
    Marks the document FAILED (and audits why) if the mapping is incomplete.
    """
    headers = list(df.columns)
    header_lookup = {h.lower(): h for h in headers}  # lowercased header -> real header text

    if set(header_lookup.keys()) == set(REQUIRED_COLUMNS.keys()):
        column_mapping = CSVColumnMapping(**{field: header_lookup[field] for field in REQUIRED_COLUMNS})
        logger.info("CSV headers matched canonically: document_id=%s", doc.id)
    else:
        sample_rows = df.head(3).to_dict(orient="records")
        column_mapping = map_columns(headers, sample_rows)
        logger.info("CSV columns mapped by agent: document_id=%s mapping=%s", doc.id, column_mapping.model_dump())

    mapping = column_mapping.model_dump()
    # Only REQUIRED_COLUMNS are actually read downstream (_parse_csv_rows) —
    # CSVColumnMapping still carries trans_type for the LLM to attempt, but a
    # miss on that alone (most bank CSVs have no debit/credit column; the
    # amount's sign already carries direction) shouldn't fail the document.
    if any(mapping[field] is None for field in REQUIRED_COLUMNS):
        logger.warning("CSV mapping incomplete: document_id=%s mapping=%s -> FAILED", doc.id, mapping)
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=doc.business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            new_values=mapping,
            reason="CSV column mapping incomplete — one or more required fields could not be resolved.",
        )
        return None
    return mapping


def _resolve_bank_account(db, business_id: int) -> Optional[int]:
    """Look up the COA leaf every CSV statement posts against for this business.

    Picking which account per-upload (multi-account businesses) is future
    work — for now every business posts CSV statements to one default leaf.
    """
    return (
        db.query(Account.id)
        .filter(Account.business_id == business_id, Account.account_code == DEFAULT_BANK_ACCOUNT_CODE)
        .scalar()
    )


def _parse_csv_rows(df: pd.DataFrame, mapping: dict) -> list[dict]:
    """Turn each raw CSV row into a plain dict of BankTransaction-shaped fields."""
    rows = []
    for _, row in df.iterrows():
        raw_amount = Decimal(str(row[mapping["amount"]]))
        description = str(row[mapping["description"]])
        # Most bank CSVs give exactly one date column — the posted/cleared
        # date, not a separate transaction date — so both fields get it.
        posted_date = pd.to_datetime(row[mapping["date"]]).date()
        rows.append({
            "transaction_date": posted_date,
            "posted_date": posted_date,
            "description": description,
            "normalized_description": _normalize(description),
            "amount": abs(raw_amount).quantize(Decimal("0.01")),
            # The amount sign is the reliable signal for bank statements:
            # negative = money out (OUTFLOW), positive = money in (INFLOW).
            "direction": CashDirection.OUTFLOW if raw_amount < 0 else CashDirection.INFLOW,
        })
    return rows


def _build_bank_transactions(
    db, *, business_id: int, account_id: int, document_id: int, parsed_rows: list[dict],
) -> tuple[list[BankTransaction], int]:
    """Fingerprint-dedupe parsed rows and build the BankTransaction objects to insert.

    Returns (rows_to_insert, duplicate_count).
    """
    if not parsed_rows:
        return [], 0

    # Only dedup against rows already covering this statement's date range —
    # scanning every fingerprint the business has ever had doesn't scale.
    date_min = min(r["posted_date"] for r in parsed_rows)
    date_max = max(r["posted_date"] for r in parsed_rows)
    seen_hashes = set(
        fp for (fp,) in db.query(BankTransaction.fingerprint_hash).filter(
            BankTransaction.business_id == business_id,
            BankTransaction.account_id == account_id,
            BankTransaction.posted_date >= date_min,
            BankTransaction.posted_date <= date_max,
        )
    )

    bank_transactions = []
    duplicate_count = 0
    for r in parsed_rows:
        fingerprint = _fingerprint(business_id, account_id, r["posted_date"], r["amount"], r["normalized_description"])
        if fingerprint in seen_hashes:
            duplicate_count += 1
            continue
        seen_hashes.add(fingerprint)  # catches duplicate rows within this same file too
        bank_transactions.append(BankTransaction(
            business_id=business_id,
            document_id=document_id,
            account_id=account_id,
            transaction_date=r["transaction_date"],
            posted_date=r["posted_date"],
            description=r["description"],
            normalized_description=r["normalized_description"],
            amount=r["amount"],
            direction=r["direction"],
            fingerprint_hash=fingerprint,
        ))
    return bank_transactions, duplicate_count


# ─────────────────────────────────────────────────────────────────────────
# PDF pipeline
# ─────────────────────────────────────────────────────────────────────────

def _process_pdf(db, business_id: int, doc: Document) -> None:
    """PDF -> Invoice+lines (we're the seller) or Bill+lines (we're the
    buyer). Mutates `doc.status` in place; every exit path also leaves an
    AuditEvent explaining the outcome."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if business is None:
        # Shouldn't happen in practice (business_id comes from an
        # already-validated route), but ingestion runs as a background task
        # decoupled from that request — don't assume the row still exists.
        logger.error("Business not found: business_id=%s document_id=%s -> FAILED", business_id, doc.id)
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            reason=f"Business {business_id} not found.",
        )
        return

    extraction = extract_document(Path(doc.file_path).read_bytes(), business.name, doc.filename)
    logger.info(
        "PDF extracted: document_id=%s seller=%r buyer=%r line_items=%d",
        doc.id, extraction.seller_name, extraction.buyer_name, len(extraction.line_items),
    )

    doc_type = _classify_pdf(business.name, extraction)
    if doc_type is None:
        logger.warning("Could not classify PDF (business name matched neither party): document_id=%s -> FAILED", doc.id)
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            new_values={"seller_name": extraction.seller_name, "buyer_name": extraction.buyer_name},
            reason="Could not determine invoice vs. bill — business name matched neither seller nor buyer.",
        )
        return
    doc.source = doc_type

    header_date = _to_date(extraction.invoice_date)
    if header_date is None:
        logger.warning("PDF missing invoice/bill date: document_id=%s -> FAILED", doc.id)
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            reason="invoice_date/bill_date not found on the document — required, cannot post without it.",
        )
        return
    due_date = _to_date(extraction.due_date)

    if doc_type == SourceType.INVOICE:
        party_id = _resolve_party(db, business_id, extraction.buyer_name, Customer)
        party_name = extraction.buyer_name
    else:
        party_id = _resolve_party(db, business_id, extraction.seller_name, Vendor)
        party_name = extraction.seller_name
    doc.party_id = party_id

    duplicate_id = _find_duplicate(
        db, business_id=business_id, doc_type=doc_type, party_id=party_id,
        invoice_number=extraction.invoice_number, party_name=party_name,
    )
    if duplicate_id is not None:
        logger.warning(
            "Duplicate %s detected (existing id=%s): document_id=%s -> FAILED",
            doc_type.value, duplicate_id, doc.id,
        )
        doc.status = DocumentStatus.FAILED
        _record_audit_event(
            db, business_id=business_id, document_id=doc.id,
            event_type=AuditEventType.FAILED,
            new_values={"duplicate_of_id": duplicate_id},
            reason=f"Duplicate {doc_type.value}: same vendor/customer + invoice_number already exists.",
        )
        return

    # A row still gets created even when we can't fully trust it yet — an
    # unresolved party or zero line items just means REVIEW_REQUIRED instead
    # of DRAFT, so a human confirms before this can be reconciled.
    needs_review = party_id is None or not extraction.line_items
    status = InvoiceBillStatus.REVIEW_REQUIRED if needs_review else InvoiceBillStatus.DRAFT

    if doc_type == SourceType.INVOICE:
        record = Invoice(
            business_id=business_id, document_id=doc.id, customer_id=party_id,
            invoice_number=extraction.invoice_number, invoice_date=header_date, due_date=due_date,
            status=status,
        )
    else:
        record = Bill(
            business_id=business_id, document_id=doc.id, vendor_id=party_id,
            bill_number=extraction.invoice_number, bill_date=header_date, due_date=due_date,
            status=status,
        )
    db.add(record)
    db.flush()  # need record.id for line items

    lines = _build_lines(record, doc_type, extraction.line_items)
    db.add_all(lines)

    # Flush so this new Invoice/Bill (+ lines) has ids and is visible to
    # reconcile()'s own queries (autoflush=False on this session). Runs
    # unconditionally — even if *this* document landed REVIEW_REQUIRED, other
    # already-open invoices/bills for the business might still be waiting on
    # a bank row that arrived earlier.
    db.flush()
    reconcile(db, business_id)

    db.add(DocumentExtraction(
        document_id=doc.id,
        extraction_type=PDF_EXTRACTION_TYPE[doc_type],
        extracted_json=extraction.model_dump(),
        model_used=settings.default_sonnet_model,
    ))
    _record_audit_event(
        db, business_id=business_id, document_id=doc.id,
        event_type=AuditEventType.EXTRACTED,
        new_values=PdfIngestionResult(
            document_type=doc_type.value,
            party_resolved=party_id is not None,
            line_item_count=len(lines),
            status=status.value,
        ).model_dump(),
    )

    doc.status = DocumentStatus.PROCESSED
    doc.processed_at = datetime.now()
    logger.info(
        "PDF processed: document_id=%s type=%s record_id=%s party_id=%s lines=%d status=%s",
        doc.id, doc_type.value, record.id, party_id, len(lines), status.value,
    )


def _classify_pdf(business_name: str, extraction) -> Optional[SourceType]:
    """Decide invoice vs. bill from which party matches the business.

    Exact normalized-name match only for now (fuzzy matching deferred —
    real invoices sometimes use a name variant, which just means those
    fall through to FAILED for manual handling rather than a guess).
    """
    name = _normalize(business_name)
    seller = _normalize(extraction.seller_name or "")
    buyer = _normalize(extraction.buyer_name or "")

    if name == seller:
        return SourceType.INVOICE       # we're the seller -> money owed to us
    if name == buyer:
        return SourceType.VENDOR_BILL   # we're the buyer -> money we owe
    return None


def _resolve_party(db, business_id: int, name: Optional[str], model) -> Optional[int]:
    """Find an existing Vendor/Customer by normalized name.

    Deliberately does NOT create a new one on a miss — an unmatched party
    means the row goes to REVIEW_REQUIRED so a human confirms/creates it,
    rather than silently adding unverified parties to the ledger.
    """
    if not name:
        return None
    return (
        db.query(model.id)
        .filter(model.business_id == business_id, model.normalized_name == _normalize(name))
        .scalar()
    )


def _find_duplicate(
    db, *, business_id: int, doc_type: SourceType, party_id: Optional[int],
    invoice_number: Optional[str], party_name: Optional[str],
) -> Optional[int]:
    """Return the id of an existing Invoice/Bill this upload duplicates, or None.

    Dedup key is (business + party + invoice_number). When the party hasn't
    resolved to an existing Vendor/Customer, falls back to comparing the
    extracted party name against other still-unresolved rows for the same
    invoice_number, so re-uploading an unresolved bill doesn't create a second one.
    """
    if not invoice_number:
        return None  # can't reliably dedup without a shared key

    if doc_type == SourceType.INVOICE:
        model, number_col, party_col = Invoice, Invoice.invoice_number, Invoice.customer_id
    else:
        model, number_col, party_col = Bill, Bill.bill_number, Bill.vendor_id

    if party_id is not None:
        return (
            db.query(model.id)
            .filter(model.business_id == business_id, number_col == invoice_number, party_col == party_id)
            .scalar()
        )

    if not party_name:
        return None

    candidates = (
        db.query(model.id, model.document_id)
        .filter(model.business_id == business_id, number_col == invoice_number, party_col.is_(None))
        .all()
    )
    target = _normalize(party_name)
    extraction_key = "buyer_name" if doc_type == SourceType.INVOICE else "seller_name"
    for record_id, document_id in candidates:
        extracted = (
            db.query(DocumentExtraction.extracted_json)
            .filter(DocumentExtraction.document_id == document_id)
            .scalar()
        )
        if extracted and _normalize(extracted.get(extraction_key) or "") == target:
            return record_id
    return None


def _build_lines(record, doc_type: SourceType, line_items) -> list:
    """Build InvoiceLine/BillLine rows for a just-created Invoice/Bill.

    Line-level account assignment (revenue_account_id / expense_account_id)
    is left null — that's a categorization-layer decision, not ingestion's.
    """
    lines = []
    for i, item in enumerate(line_items, start=1):
        fields = dict(
            line_number=i,
            description=item.description,
            quantity=_to_decimal(item.quantity) or Decimal("1"),
            unit_price=_to_decimal(item.net_price) or Decimal("0"),
            tax_amount=_to_decimal(item.tax_amount) or Decimal("0"),
        )
        if doc_type == SourceType.INVOICE:
            lines.append(InvoiceLine(invoice_id=record.id, **fields))
        else:
            lines.append(BillLine(bill_id=record.id, **fields))
    return lines


def _to_date(value: Optional[str]) -> Optional[date]:
    """Parse a 'YYYY-MM-DD' string into a date, or None if missing/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _to_decimal(value) -> Optional[Decimal]:
    return Decimal(str(value)) if value is not None else None


# ─────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────

def _record_audit_event(
    db,
    *,
    business_id: int,
    document_id: int,
    event_type: AuditEventType,
    new_values: Optional[dict] = None,
    reason: Optional[str] = None,
) -> None:
    """Append an audit-trail row for a document-level ingestion outcome."""
    db.add(AuditEvent(
        business_id=business_id,
        entity_type="document",
        entity_id=document_id,
        event_type=event_type,
        actor_type=AuditActorType.SYSTEM,
        new_values=new_values,
        reason=reason,
    ))


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _fingerprint(business_id: int, account_id: int, transaction_date, amount: Decimal, normalized_description: str) -> str:
    raw = f"{business_id}:{account_id}:{transaction_date.isoformat()}:{amount}:{normalized_description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
