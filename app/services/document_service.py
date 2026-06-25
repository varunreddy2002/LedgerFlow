"""Document service — file storage and document row management."""

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.enums import DocumentStatus, SourceType
from app.models.transaction import Transaction
from app.services.csv_parser import ParseResult


class DocumentService:
    """Handles file I/O and document DB rows.

    All path logic is centralised here — routes never touch the filesystem.

    Usage:
        svc = DocumentService()
        content, checksum = await svc.read_and_checksum(file)
        stored_name, path  = svc.save_to_disk(content, business_id, filename)
        doc                = svc.create_document(db, ...)
    """

    def __init__(self) -> None:
        self.upload_dir = Path(settings.upload_dir)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def read_and_checksum(self, file: UploadFile) -> tuple[bytes, str]:
        """Read the entire upload into memory and return (content, sha256_hex)."""
        content = await file.read()
        checksum = hashlib.sha256(content).hexdigest()
        return content, checksum

    def get_by_checksum(self, db: Session, business_id: int, checksum: str) -> Document | None:
        """Return an existing document with the same content hash, or None."""
        return (
            db.query(Document)
            .filter(
                Document.business_id == business_id,
                Document.sha256_checksum == checksum,
            )
            .first()
        )

    def save_to_disk(self, content: bytes, business_id: int, original_filename: str) -> tuple[str, str]:
        """Write bytes to  uploads/{business_id}/{uuid}.{ext}.

        Returns:
            (stored_filename, absolute_file_path)
        """
        ext = Path(original_filename).suffix.lower()
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        dir_path = self._business_dir(business_id)
        file_path = dir_path / stored_filename
        file_path.write_bytes(content)
        return stored_filename, str(file_path)

    def create_document(
        self,
        db: Session,
        *,
        business_id: int,
        original_filename: str,
        stored_filename: str,
        file_path: str,
        file_size: int,
        checksum: str,
        file_ext: str,
    ) -> Document:
        """Insert a documents row and flush so doc.id is available.

        Status defaults:
          .csv  → UPLOADED    (parsed synchronously in the same request)
          .pdf  → PENDING_OCR (async OCR pipeline)
        """
        ext = file_ext.lower().lstrip(".")
        status = DocumentStatus.UPLOADED if ext == "csv" else DocumentStatus.PENDING_OCR
        source_type = SourceType.BANK_STATEMENT if ext == "csv" else SourceType.UNKNOWN

        doc = Document(
            business_id=business_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            sha256_checksum=checksum,
            file_type=ext,
            source_type=source_type,
            status=status,
        )
        db.add(doc)
        db.flush()
        return doc

    def get_existing_fingerprints(self, db: Session, business_id: int) -> set[str]:
        """Return all fingerprint hashes already stored for this business."""
        return {
            fp
            for (fp,) in db.query(Transaction.fingerprint_hash).filter(
                Transaction.business_id == business_id,
                Transaction.fingerprint_hash.isnot(None),
            )
        }

    def apply_csv_status(self, doc: Document, result: ParseResult) -> None:
        """Set document status after CSV parsing.

        Fatal header error (row_number == 0) → FAILED
        Everything else                       → CATEGORIZING
        """
        if any(e.row_number == 0 for e in result.errors):
            doc.status = DocumentStatus.FAILED
        else:
            doc.status = DocumentStatus.CATEGORIZING

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _business_dir(self, business_id: int) -> Path:
        """Return (and create if missing) the upload directory for a business."""
        path = self.upload_dir / str(business_id)
        path.mkdir(parents=True, exist_ok=True)
        return path
