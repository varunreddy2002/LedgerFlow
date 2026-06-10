"""Uploaded source files and the structured data extracted from them."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.models.enums import DocumentStatus, SourceType
from app.models.mixins import CreatedAtMixin, enum_column


class Document(Base):
    __tablename__ = "documents"
    # Same file (by content hash) can never be ingested twice for one business.
    __table_args__ = (
        UniqueConstraint("business_id", "sha256_checksum", name="uq_document_business_checksum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(50))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[SourceType] = enum_column(
        SourceType, default=SourceType.unknown, nullable=False
    )
    status: Mapped[DocumentStatus] = enum_column(
        DocumentStatus, default=DocumentStatus.uploaded, nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    business: Mapped["Business"] = relationship(back_populates="documents")
    extractions: Mapped[List["DocumentExtraction"]] = relationship(
        back_populates="document"
    )
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="document")


class DocumentExtraction(Base, CreatedAtMixin):
    __tablename__ = "document_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True, nullable=False
    )
    extraction_type: Mapped[Optional[str]] = mapped_column(String(100))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSON)
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    confidence_score: Mapped[Optional[float]] = mapped_column()

    document: Mapped["Document"] = relationship(back_populates="extractions")
