from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.db.database import Base
from app.domain.models.mixins import CreatedAtMixin, PrimaryKeyMixin, TimestampMixin, enum_column
from app.domain.enums import DocumentStatus, SourceType


class Document(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True, nullable=False)
    party_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[SourceType] = enum_column(SourceType, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = enum_column(DocumentStatus, default=DocumentStatus.UPLOADED, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="documents")
    extractions: Mapped[List["DocumentExtraction"]] = relationship(back_populates="document")


class DocumentExtraction(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_extractions"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)
    extraction_type: Mapped[Optional[str]] = mapped_column(String(100))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSON)
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    confidence_score: Mapped[Optional[float]] = mapped_column()

    document: Mapped["Document"] = relationship(back_populates="extractions")


from app.domain.models.business import Business  # noqa: E402,F401
