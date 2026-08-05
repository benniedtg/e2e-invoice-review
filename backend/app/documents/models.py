"""SQLAlchemy ORM tables; the Pydantic document models live in app/schemas/."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.document_review import apply_field_overrides
from app.pipeline import PipelineResult
from app.schemas import DocumentType, InvoiceDocument, NormalizedDocument, ReceiptDocument


class ReviewStatus(StrEnum):
  """Where one stored document stands in the human review workflow."""

  PENDING = "pending"
  APPROVED = "approved"
  REJECTED = "rejected"


class Base(DeclarativeBase):
  """Declarative base for every stored table."""


def _utc_now() -> datetime:
  """Return the current time as an aware UTC value."""
  return datetime.now(UTC)


class DocumentRecord(Base):
  """One processed document with each pipeline stage kept separately."""

  __tablename__ = "documents"
  __table_args__ = (
    Index("ix_documents_duplicate_key", "vendor_name_key", "invoice_number_key"),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True)
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=_utc_now,
    index=True,
  )

  original_filename: Mapped[str] = mapped_column(String(255))
  content_type: Mapped[str] = mapped_column(String(64))
  size_bytes: Mapped[int] = mapped_column(Integer)
  sha256: Mapped[str] = mapped_column(String(64), index=True)

  status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.PENDING)
  review_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
  pipeline_status: Mapped[str] = mapped_column(String(16))

  classification: Mapped[dict[str, Any]] = mapped_column(JSON)
  extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
  independent_review: Mapped[dict[str, Any] | None] = mapped_column(
    JSON,
    nullable=True,
  )
  reconciliation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
  merged_document: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
  gl_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
  validation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

  document_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
  vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
  invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
  vendor_name_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
  invoice_number_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
  duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

  selected_gl_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
  field_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
  reviewed_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True),
    nullable=True,
  )

  def to_pipeline_result(self) -> PipelineResult:
    """Rebuild the strict result so its terminal-state rules are re-applied."""
    document = self._effective_document()
    return PipelineResult.model_validate(
      {
        "status": self.pipeline_status,
        "classification": self.classification,
        "independent_review": self.independent_review,
        "primary_document": self.extraction,
        "reconciliation": self.reconciliation,
        "document": document,
        "general_ledger": self.gl_suggestion,
        "validation": self.validation,
      }
    )

  def _effective_document(self) -> NormalizedDocument | None:
    """Apply mutable human fields over the immutable merged document."""
    if self.merged_document is None:
      return None
    document_type = self.merged_document.get("document_type")
    if document_type == DocumentType.INVOICE:
      merged: NormalizedDocument = InvoiceDocument.model_validate(
        self.merged_document
      )
    elif document_type == DocumentType.RECEIPT:
      merged = ReceiptDocument.model_validate(self.merged_document)
    else:
      raise ValueError("Stored merged document has an unsupported document type.")
    return apply_field_overrides(merged, self.field_overrides)
