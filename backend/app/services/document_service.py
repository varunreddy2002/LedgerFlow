"""File storage and document-row helpers.

Responsibilities:
  - Compute SHA-256 checksums for uploaded files
  - Save raw bytes to  uploads/{business_id}/{uuid}.{ext}
  - Look up existing documents by checksum (duplicate-file guard)
  - Create the ``documents`` DB row (flush only — caller commits)

No CSV parsing lives here; that is the job of ``csv_parser``.
"""

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.enums import DocumentStatus, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _upload_dir(business_id: int) -> Path:
    """Return (and create) the upload directory for a given business."""
    path = Path(settings.upload_dir) / str(business_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def read_and_checksum(file: UploadFile) -> tuple[bytes, str]:
    """Read the entire upload into memory and return (content, sha256_hex)."""
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    return content, checksum


def get_by_checksum(db: Session, business_id: int, checksum: str) -> Document | None:
    """Return an existing document that has the same content hash, or None."""
    return (
        db.query(Document)
        .filter(
            Document.business_id == business_id,
            Document.sha256_checksum == checksum,
        )
        .first()
    )


def save_to_disk(content: bytes, business_id: int, original_filename: str) -> tuple[str, str]:
    """Write bytes to disk under the configured upload directory.

    Returns:
        (stored_filename, absolute_file_path)
    """
    ext = _ext(original_filename)
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = _upload_dir(business_id) / stored_filename
    file_path.write_bytes(content)
    return stored_filename, str(file_path)


def create_document(
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
    """Insert a ``documents`` row and flush so ``doc.id`` is available.

    Status is set based on file type:
      .csv  → ``uploaded``    (will be parsed synchronously in the same request)
      .pdf  → ``pending_ocr`` (async OCR pipeline, not yet implemented)
    """
    ext = file_ext.lower().lstrip(".")
    status = DocumentStatus.UPLOADED if ext == "csv" else DocumentStatus.PENDING_OCR

    doc = Document(
        business_id=business_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size=file_size,
        sha256_checksum=checksum,
        file_type=ext,
        source_type=SourceType.UNKNOWN,
        status=status,
    )
    db.add(doc)
    db.flush()  # assigns doc.id; caller is responsible for commit
    return doc
