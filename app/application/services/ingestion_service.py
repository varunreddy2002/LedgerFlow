from pathlib import Path
import hashlib
import re
import pandas as pd
from datetime import date, datetime
from decimal import Decimal
from app.application.agents import map_columns, extract_document
from app.infrastructure.db import session_scope
from app.domain.models import Document
from app.domain.enums import DocumentStatus, SourceType
from app.core.config import settings
from app.domain.enums import TransactionType, ReviewStatus
from app.domain.models import Document, Transaction, Business, TransactionLineItem, DocumentExtraction, Customer, Vendor
from app.core.logging import get_logger
from app.domain.schemas import CSVColumnMapping
from app.application.agents.categorization import run_categorization

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent.parent
UPLOAD_DIR = ROOT_DIR / "uploads"

def run_ingestion(business_id: int, filename: str, content: bytes, ext: str):
    logger.info("Ingestion started: business_id=%s filename=%s ext=%s", business_id, filename, ext)

    file_path = UPLOAD_DIR / str(business_id) / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)

    with session_scope() as db:
        doc = Document(
            business_id=business_id,
            filename=filename,
            file_path=str(file_path),
            source=SourceType.BANK_STATEMENT if ext == ".csv" else SourceType.VENDOR_BILL,
            status=DocumentStatus.PROCESSING,
            sha256_checksum=_checksum(content),
        )

        db.add(doc)
        db.flush()
        logger.info("Document row created: document_id=%s status=%s", doc.id, doc.status)

        if ext == ".csv":
            _process_csv(db, business_id, doc, file_path)       
        elif ext == ".pdf":
            _process_pdf(db, business_id, doc, file_path, filename)
        final_status = doc.status
        logger.info("Ingestion finished: document_id=%s final_status=%s", doc.id, doc.status)

    if final_status == DocumentStatus.PROCESSED:
        run_categorization(business_id)


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def _process_csv(db, business_id: int, doc, file_path: Path):
    df = pd.read_csv(file_path)
    headers = list(df.columns)

    # canonical fields we need to populate a Transaction
    required_columns = {
        "date": "the date when the transaction was posted or occurred",
        "description": "the narration or merchant name or transaction description",
        "amount": "the transaction amount, can be negative for debits",
        "trans_type": "indicates if the transaction is a debit or credit",
    }

    # header_lookup maps lowercased name -> actual column name as it appears in the file
    header_lookup = {h.lower(): h for h in headers}

    if set(header_lookup.keys()) == set(required_columns.keys()):
        # headers already match our shape — map each field to its real column name
        column_mapping = CSVColumnMapping(**{k: header_lookup[k] for k in required_columns})
        logger.info("CSV headers matched canonically: document_id=%s", doc.id)
    else:
        # headers differ — let the agent figure out the mapping
        data_chunk = df.head(3).to_dict(orient="records")
        column_mapping = map_columns(headers, data_chunk)
        logger.info("CSV columns mapped by agent: document_id=%s mapping=%s", doc.id, column_mapping.model_dump())

    mapping = column_mapping.model_dump()
    if None in mapping.values():
        logger.warning("CSV mapping incomplete: document_id=%s mapping=%s -> FAILED", doc.id, mapping)
        doc.status = DocumentStatus.FAILED
        return

    transactions = []
    for _, row in df.iterrows():
        raw_amount = Decimal(str(row[mapping["amount"]]))

        # The amount sign is the reliable signal for bank statements:
        # negative = money out (DEBIT), positive = money in (CREDIT).
        trans_type = TransactionType.DEBIT if raw_amount < 0 else TransactionType.CREDIT

        transactions.append(Transaction(
            document_id=doc.id,
            date=pd.to_datetime(row[mapping["date"]]).date(),
            description=str(row[mapping["description"]]),
            amount=abs(raw_amount),
            trans_type=trans_type,
        ))

    db.add_all(transactions)
    doc.status = DocumentStatus.PROCESSED
    doc.processed_at = datetime.now()
    logger.info("CSV processed: document_id=%s transactions=%d", doc.id, len(transactions))
    # fingerprint hash intentionally skipped for now
        




def _process_pdf(db, business_id: int, doc, file_path: Path, filename: str):
    business = db.query(Business).filter(Business.id == business_id).first()
    if business is None:
        doc.status = DocumentStatus.FAILED
        return

    business_name = business.name
    pdf_bytes = file_path.read_bytes()

    extraction = extract_document(pdf_bytes, business_name, filename)
    logger.info(
        "Extraction done: document_id=%s seller=%s buyer=%s line_items=%d",
        doc.id, extraction.seller_name, extraction.buyer_name, len(extraction.line_items),
    )

    # both parties must be present, else we can't classify reliably
    if not extraction.seller_name or not extraction.buyer_name:
        logger.warning("Classification skipped: missing party. document_id=%s -> FAILED", doc.id)
        doc.status = DocumentStatus.FAILED
        return

    classification = _classify(business_name, extraction)
    if classification is None:
        logger.warning("Could not classify (business name matches neither party). document_id=%s -> FAILED", doc.id)
        doc.status = DocumentStatus.FAILED
        return
    doc_type, transaction_type = classification
    logger.info("Classified document_id=%s as %s (%s)", doc.id, doc_type.value, transaction_type.value)

    if doc_type == SourceType.INVOICE:
        party_id = _upsert_party(db, business_id, extraction.buyer_name, Customer)
    else:  # VENDOR_BILL
        party_id = _upsert_party(db, business_id, extraction.seller_name, Vendor)

    doc.party_id = party_id

    txn = Transaction(
        document_id=doc.id,
        vendor_id=party_id if doc_type == SourceType.VENDOR_BILL else None,
        customer_id=party_id if doc_type == SourceType.INVOICE else None,
        date=_to_date(extraction.invoice_date),
        due_date=_to_date(extraction.due_date),
        amount=_to_decimal(extraction.total_amount or 0),
        trans_type=transaction_type,
        description=extraction.seller_name,
    )
    
    db.add(txn)
    doc.source = doc_type
    db.flush()   # need txn.id for line items

    # Transaction Line Items
    line_items = [
    TransactionLineItem(
        transaction_id=txn.id,
        description=item.description,
        quantity=_to_decimal(item.quantity),
        unit_price=_to_decimal(item.net_price),
        tax_amount=_to_decimal(item.tax_amount),
    )
    for item in extraction.line_items
    ]
    db.add_all(line_items)

    db.add(DocumentExtraction(
    document_id=doc.id,
    extraction_type=doc_type.value,
    extracted_json=extraction.model_dump(),
    model_used=settings.default_sonnet_model,
    ))

    doc.status = DocumentStatus.PROCESSED
    doc.processed_at = datetime.now()
    logger.info(
        "PDF processed: document_id=%s txn_id=%s amount=%s line_items=%d party_id=%s",
        doc.id, txn.id, txn.amount, len(line_items), party_id,
    )

    # raw_text and confidence is not set yet.



def _to_date(value: str | None) -> date | None:
    """Convert a 'YYYY-MM-DD' string into a date, or None if empty/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
    
def _to_decimal(value) -> Decimal | None:
    """Convert a number (or None) into a Decimal for safe money storage."""
    return Decimal(str(value)) if value is not None else None


def _classify(business_name: str, extraction) -> tuple[SourceType, TransactionType] | None:
    name = _normalize(business_name)
    seller = _normalize(extraction.seller_name or "")
    buyer = _normalize(extraction.buyer_name or "")

    if name == seller:
        return SourceType.INVOICE, TransactionType.RECEIVABLE    # we sold → money in
    if name == buyer:
        return SourceType.VENDOR_BILL, TransactionType.PAYABLE   # we bought → money out
    return None                                                  # can't tell


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _upsert_party(db, business_id: int, name: str, model):
    """Find vendor/customer by exact normalized name, or create it. Returns its id."""
    normalized = _normalize(name)
    existing = db.query(model).filter(model.business_id == business_id).all()

    for record in existing:
        if _normalize(record.name) == normalized:
            logger.info("Party matched: model=%s id=%s name=%r", model.__name__, record.id, record.name)
            return record.id

    party = model(business_id=business_id, name=name)
    db.add(party)
    db.flush()
    logger.info("Party created: model=%s id=%s name=%r", model.__name__, party.id, name)
    return party.id