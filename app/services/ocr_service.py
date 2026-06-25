"""OCR service — single-pass invoice extraction using h2oai/h2ovl-mississippi-800m.

The model works best with an explicit JSON template (nulls pre-filled).
It fills in the blanks rather than reasoning about structure.
"""

import base64
import hashlib
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import fitz
import requests

from app.core.config import settings
from app.schemas.invoice_schema import InvoiceExtraction, LineItem

logger = logging.getLogger(__name__)

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]

_PROMPT = """\
Extract invoice data from the image.

Return JSON only.
Do not explain.
Do not add extra keys.
Do not guess.
Use null if a value is not visible.

Extract:

* vendor_name
* invoice_number
* invoice_date in YYYY-MM-DD format
* due_date in YYYY-MM-DD format

For each line item, extract only:

* description: item name
* quantity: quantity of the item
* net_price: price per single unit before tax

Return exactly this format:

{
"vendor_name": null,
"invoice_number": null,
"invoice_date": null,
"due_date": null,
"line_items": [
{
"description": null,
"quantity": null,
"net_price": null
}
]
}

"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d,.]', '', value.strip())
        if not cleaned:
            return None
        if ',' in cleaned and '.' not in cleaned:
            cleaned = cleaned.replace(',', '.')
        elif ',' in cleaned and '.' in cleaned:
            if cleaned.rindex(',') > cleaned.rindex('.'):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_date(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# OCR Service
# ---------------------------------------------------------------------------

class OCRService:
    def __init__(self):
        self.url = f"{settings.vllm_base_url.rstrip('/')}/v1/chat/completions"
        self.model = settings.ocr_model
        print(f"[OCR] Endpoint : {self.url}")
        print(f"[OCR] Model    : {self.model}")

    def _pdf_to_images(self, file_path: str) -> list[str]:
        doc = fitz.open(file_path)
        images = []
        mat = fitz.Matrix(2.0, 2.0)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            images.append(base64.b64encode(pix.tobytes("png")).decode())
        doc.close()
        return images

    @staticmethod
    def _clean_json(raw: str) -> str:
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return raw[start:end + 1]
        return raw

    def _call(self, image_b64: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
            "max_tokens": 2048,
            "temperature": 0.0,
        }
        print(f"[OCR] POST {self.url}")
        r = requests.post(self.url, json=payload, timeout=120)
        print(f"[OCR] Response status: {r.status_code}")
        if not r.ok:
            logger.warning("OCR HTTP error %s: %s", r.status_code, r.text[:200])
            return {}
        raw = r.json()["choices"][0]["message"]["content"].strip()
        print(f"[OCR] Raw response: {raw[:300]}")
        cleaned = self._clean_json(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("OCR returned invalid JSON: %s", raw[:200])
            return {}

    def extract_invoice(self, file_path: str) -> InvoiceExtraction:
        images = self._pdf_to_images(file_path)
        result = InvoiceExtraction()

        for page_num, img in enumerate(images, 1):
            logger.info("OCR page %d/%d — %s", page_num, len(images), file_path)
            data = self._call(img)

            # Scalars — first non-null value across pages wins
            if result.vendor_name is None:
                result.vendor_name = data.get("vendor_name") or None
            if result.invoice_number is None:
                raw_num = data.get("invoice_number")
                result.invoice_number = str(raw_num) if raw_num is not None else None
            if result.invoice_date is None:
                result.invoice_date = _parse_date(data.get("invoice_date"))
            if result.due_date is None:
                result.due_date = _parse_date(data.get("due_date"))

            # Line items — accumulate across all pages
            for item in data.get("line_items", []):
                description = item.get("description")
                if not description:
                    continue

                qty = _normalize_number(item.get("quantity"))
                net_price = _normalize_number(item.get("net_price"))

                if qty is None or net_price is None:
                    continue

                try:
                    amount = abs(Decimal(str(qty)) * Decimal(str(net_price)))
                    result.line_items.append(LineItem(
                        description=str(description).strip(),
                        amount=amount,
                    ))
                except (InvalidOperation, TypeError):
                    logger.warning("Could not compute amount for line item: %s", item)

        return result


# ---------------------------------------------------------------------------
# Background task entry point — same pattern as categorize_transactions
# ---------------------------------------------------------------------------

def process_pdf_document(document_id: int, business_id: int) -> None:
    """Called by FastAPI BackgroundTasks after a PDF is uploaded."""
    from app.db.database import SessionLocal
    from app.models.business import Vendor
    from app.models.document import Document, DocumentExtraction
    from app.models.enums import Direction, DocumentStatus, ReviewStatus, SourceType, TransactionType
    from app.models.transaction import Transaction
    from app.services.categorization_service import categorize_transactions

    db = SessionLocal()
    should_categorize = False

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("process_pdf_document: document %s not found", document_id)
            return

        doc.status = DocumentStatus.PROCESSING
        db.commit()

        extraction = OCRService().extract_invoice(doc.file_path)

        # Audit trail — store raw extraction JSON
        db.add(DocumentExtraction(
            document_id=document_id,
            extraction_type="invoice",
            extracted_json=extraction.model_dump(mode="json"),
            model_used=settings.ocr_model,
        ))

        # Update document metadata
        doc.invoice_number = extraction.invoice_number
        doc.invoice_date = extraction.invoice_date
        doc.due_date = extraction.due_date
        doc.source_type = SourceType.VENDOR_BILL
        doc.processed_at = datetime.utcnow()

        # Upsert vendor
        vendor_id = None
        if extraction.vendor_name:
            normalized = extraction.vendor_name.strip().lower()
            vendor = db.query(Vendor).filter(
                Vendor.business_id == business_id,
                Vendor.normalized_name == normalized,
            ).first()
            if not vendor:
                vendor = Vendor(
                    business_id=business_id,
                    name=extraction.vendor_name.strip(),
                    normalized_name=normalized,
                )
                db.add(vendor)
                db.flush()
            vendor_id = vendor.id

        # Load existing fingerprints for dedup
        existing_fps: set[str] = {
            fp for (fp,) in db.query(Transaction.fingerprint_hash).filter(
                Transaction.business_id == business_id,
                Transaction.fingerprint_hash.isnot(None),
            )
        }

        txn_date = extraction.invoice_date or datetime.utcnow().date()
        txns = []
        for item in extraction.line_items:
            raw_fp = f"{business_id}:{txn_date.isoformat()}:{item.description.strip().lower()}:{abs(item.amount)}"
            fp = hashlib.sha256(raw_fp.encode()).hexdigest()
            if fp in existing_fps:
                continue
            existing_fps.add(fp)
            txns.append(Transaction(
                business_id=business_id,
                document_id=document_id,
                transaction_date=txn_date,
                description_raw=item.description,
                merchant_name=extraction.vendor_name,
                vendor_id=vendor_id,
                amount=abs(item.amount),
                direction=Direction.OUTFLOW,
                transaction_type=TransactionType.EXPENSE,
                review_status=ReviewStatus.NEEDS_REVIEW,
                fingerprint_hash=fp,
                is_excluded_from_pnl=False,
            ))

        if txns:
            db.add_all(txns)
            doc.status = DocumentStatus.CATEGORIZING
            should_categorize = True
        else:
            doc.status = DocumentStatus.PROCESSED

        db.commit()
        logger.info("process_pdf_document: document %s — %d transactions created", document_id, len(txns))

    except Exception:
        logger.exception("process_pdf_document failed for document_id=%s", document_id)
        db.rollback()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = DocumentStatus.FAILED
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

    if should_categorize:
        categorize_transactions(business_id, document_id)
