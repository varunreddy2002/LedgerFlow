"""OCR service — extracts transactions from PDF invoices via a vLLM endpoint."""

import base64
import hashlib
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import fitz  # PyMuPDF
import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.enums import Direction, DocumentStatus, ReviewStatus, TransactionType
from app.models.transaction import Transaction
from app.services.categorization_service import categorize_transactions

logger = logging.getLogger(__name__)


class OCRService:
    """Converts PDF invoices to transactions using a vLLM vision model.

    Usage:
        OCRService().run(business_id, document_id)
    """

    _MODEL = "h2oai/h2ovl-mississippi-800m"

    _PROMPT = (
        "Extract all data from this invoice. "
        "Output ONLY a raw JSON object. "
        "No markdown, no code blocks, no backticks, no explanation. "
        "Start your response with { and end with }. "
        "Fields: invoice_number, invoice_date, due_date, "
        "vendor (name, address, email, phone), "
        "client (name, address), "
        "line_items (array of: description, quantity, unit_price, amount), "
        "subtotal, tax, total, currency. "
        "Read the ACTUAL numbers from the document — do not use 0.00 as a placeholder. "
        "Extract every single line item without skipping any."
    )

    def __init__(self) -> None:
        self.url = settings.vllm_base_url
        self.api_key = settings.vllm_api_key

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, business_id: int, document_id: int) -> None:
        """Entry point — manages its own DB session."""
        db: Session = SessionLocal()
        try:
            self._process(db, business_id, document_id)
        except Exception:
            logger.exception("OCR failed for document_id=%s business_id=%s", document_id, business_id)
            db.rollback()
            self._mark_failed(db, document_id)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Private — processing pipeline
    # ------------------------------------------------------------------

    def _process(self, db: Session, business_id: int, document_id: int) -> None:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("Document %s not found.", document_id)
            return

        if not self.url:
            logger.error("VLLM_BASE_URL not set — cannot run OCR.")
            self._mark_failed(db, document_id)
            return

        pages_b64 = self._pdf_to_images(doc.file_path)
        if not pages_b64:
            logger.error("Could not convert PDF to images for document %s.", document_id)
            self._mark_failed(db, document_id)
            return

        all_line_items: list[dict] = []
        invoice_date: Optional[date] = None

        for page_num, img_b64 in enumerate(pages_b64):
            logger.info("OCR: processing page %d of document %s", page_num + 1, document_id)
            raw = self._call_model(img_b64)
            parsed = self._parse_response(raw)
            if not parsed:
                logger.warning("Page %d returned no parseable JSON.", page_num + 1)
                continue
            if invoice_date is None:
                invoice_date = self._parse_date(parsed.get("invoice_date"))
            all_line_items.extend(parsed.get("line_items") or [])

        if not all_line_items:
            logger.warning("No line items extracted from document %s.", document_id)
            self._mark_failed(db, document_id)
            return

        self._save_transactions(db, business_id, document_id, all_line_items, invoice_date)

        doc.status = DocumentStatus.CATEGORIZING
        db.commit()

        categorize_transactions(business_id, document_id)

    def _save_transactions(
        self,
        db: Session,
        business_id: int,
        document_id: int,
        line_items: list[dict],
        invoice_date: Optional[date],
    ) -> None:
        txn_date = invoice_date or date.today()
        existing_fps = self._get_existing_fingerprints(db, business_id)

        for item in line_items:
            description = str(item.get("description") or "").strip()
            amount = self._to_decimal(item.get("amount") or item.get("unit_price") or 0)

            if not description:
                continue

            fp = self._fingerprint(business_id, document_id, description, amount)
            if fp in existing_fps:
                logger.debug("Skipping duplicate line item: %s", description)
                continue

            db.add(Transaction(
                business_id=business_id,
                document_id=document_id,
                account_id=None,
                transaction_date=txn_date,
                description_raw=description,
                amount=amount,
                direction=Direction.INFLOW,
                transaction_type=TransactionType.UNKNOWN,
                review_status=ReviewStatus.NEEDS_REVIEW,
                fingerprint_hash=fp,
                is_excluded_from_pnl=False,
            ))
            existing_fps.add(fp)

    # ------------------------------------------------------------------
    # Private — helpers
    # ------------------------------------------------------------------

    def _pdf_to_images(self, file_path: str) -> list[str]:
        try:
            pdf = fitz.open(file_path)
            images = []
            for page in pdf:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
                images.append(base64.b64encode(pix.tobytes("png")).decode())
            pdf.close()
            return images
        except Exception:
            logger.exception("Failed to convert PDF to images: %s", file_path)
            return []

    def _call_model(self, image_b64: str) -> str:
        payload = {
            "model": self._MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": self._PROMPT},
                ],
            }],
            "max_tokens": 1500,
            "temperature": 0.0,
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{self.url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str) -> Optional[dict[str, Any]]:
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from OCR response.")
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
        return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")

    @staticmethod
    def _fingerprint(business_id: int, document_id: int, description: str, amount: Decimal) -> str:
        raw = f"{business_id}|{document_id}|{description.lower()}|{amount}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _get_existing_fingerprints(db: Session, business_id: int) -> set[str]:
        return {
            fp for (fp,) in db.query(Transaction.fingerprint_hash).filter(
                Transaction.business_id == business_id,
                Transaction.fingerprint_hash.isnot(None),
            )
        }

    @staticmethod
    def _mark_failed(db: Session, document_id: int) -> None:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.FAILED
            db.commit()


# ---------------------------------------------------------------------------
# BackgroundTask entry point — thin wrapper around the service class
# ---------------------------------------------------------------------------

def process_pdf_document(business_id: int, document_id: int) -> None:
    """Called by FastAPI BackgroundTasks after a PDF upload."""
    OCRService().run(business_id, document_id)
