from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.documents.keys import DocumentIdentity
from app.documents.models import DocumentRecord, ReviewStatus
from app.invoices import ValidationReport


class DocumentNotFoundError(Exception):
  """No stored document exists for the requested identifier."""


class StaleReviewWriteError(Exception):
  """A review mutation lost an optimistic-concurrency race."""


@dataclass(frozen=True, slots=True)
class DocumentRecordSnapshot:
  """Detached column values used only to compensate a failed file cleanup."""

  values: dict[str, object]


def create_document(session: Session, record: DocumentRecord) -> DocumentRecord:
  """Insert one processed document and return the stored row."""
  session.add(record)
  session.commit()
  session.refresh(record)
  return record


def list_documents(session: Session) -> Sequence[DocumentRecord]:
  """Return every stored document, newest first."""
  statement = select(DocumentRecord).order_by(DocumentRecord.created_at.desc())
  return session.scalars(statement).all()


def get_document(session: Session, document_id: str) -> DocumentRecord:
  """Return one stored document or report that the identifier is unknown."""
  record = session.get(DocumentRecord, document_id)
  if record is None:
    raise DocumentNotFoundError("No document exists for that identifier.")
  return record


def delete_document(session: Session, document_id: str) -> DocumentRecord:
  """Remove one stored row and return it so its file can be removed too."""
  record = get_document(session, document_id)
  session.delete(record)
  try:
    session.commit()
  except Exception:
    try:
      session.rollback()
    except Exception:  # noqa: BLE001 - preserve the original commit failure
      pass
    raise
  return record


def snapshot_document(record: DocumentRecord) -> DocumentRecordSnapshot:
  """Copy every persisted column before a recoverable two-resource delete."""
  return DocumentRecordSnapshot(values={
    column.name: deepcopy(getattr(record, column.name))
    for column in DocumentRecord.__table__.columns
  })


def restore_deleted_document(
  session: Session,
  snapshot: DocumentRecordSnapshot,
) -> DocumentRecord:
  """Reinsert a committed-deleted row so its staged source remains retryable."""
  record = DocumentRecord(**deepcopy(snapshot.values))
  session.add(record)
  try:
    session.commit()
  except Exception:
    try:
      session.rollback()
    except Exception:  # noqa: BLE001 - preserve the compensation commit failure
      pass
    raise
  session.refresh(record)
  return record


def find_duplicate_by_content(
  session: Session,
  sha256: str,
  exclude_id: str | None = None,
) -> DocumentRecord | None:
  """Find the earliest stored document with byte-identical content."""
  statement = select(DocumentRecord).where(DocumentRecord.sha256 == sha256)
  if exclude_id is not None:
    statement = statement.where(DocumentRecord.id != exclude_id)
  statement = statement.order_by(DocumentRecord.created_at).limit(1)
  return session.scalars(statement).first()


def find_duplicate_by_key(
  session: Session,
  vendor_name_key: str,
  invoice_number_key: str,
  exclude_id: str | None = None,
) -> DocumentRecord | None:
  """Find the earliest invoice already stored under the same supplier key."""
  statement = select(DocumentRecord).where(
    DocumentRecord.vendor_name_key == vendor_name_key,
    DocumentRecord.invoice_number_key == invoice_number_key,
  )
  if exclude_id is not None:
    statement = statement.where(DocumentRecord.id != exclude_id)
  statement = statement.order_by(DocumentRecord.created_at).limit(1)
  return session.scalars(statement).first()


def save_corrections(
  session: Session,
  record: DocumentRecord,
  *,
  expected_revision: int,
  field_overrides: dict[str, object],
  validation: ValidationReport,
  identity: DocumentIdentity,
  duplicate_of_id: str | None,
) -> DocumentRecord:
  """Atomically store effective review fields and their derived policy state."""
  return _save_pending_review_update(
    session,
    record,
    expected_revision=expected_revision,
    updates={
      "field_overrides": deepcopy(field_overrides),
      "validation": validation.model_dump(mode="json"),
      "vendor_name": identity.vendor_name,
      "invoice_number": identity.invoice_number,
      "vendor_name_key": identity.vendor_name_key,
      "invoice_number_key": identity.invoice_number_key,
      "duplicate_of_id": duplicate_of_id,
    },
  )


def select_gl_code(
  session: Session,
  record: DocumentRecord,
  account_code: str,
  expected_revision: int,
) -> DocumentRecord:
  """Store one explicit human GL selection in a single transaction."""
  return _save_pending_review_update(
    session,
    record,
    expected_revision=expected_revision,
    updates={"selected_gl_code": account_code},
  )


def set_review_decision(
  session: Session,
  record: DocumentRecord,
  status: ReviewStatus,
  reviewed_at: datetime,
  expected_revision: int,
) -> DocumentRecord:
  """Finalize one review status and timestamp in a single transaction."""
  return _save_pending_review_update(
    session,
    record,
    expected_revision=expected_revision,
    updates={"status": status.value, "reviewed_at": reviewed_at},
  )


def _save_pending_review_update(
  session: Session,
  record: DocumentRecord,
  *,
  expected_revision: int,
  updates: dict[str, object],
) -> DocumentRecord:
  """Commit one pending revision or reject a stale review snapshot."""
  statement = (
    update(DocumentRecord)
    .where(
      DocumentRecord.id == record.id,
      DocumentRecord.status == ReviewStatus.PENDING.value,
      DocumentRecord.review_revision == expected_revision,
    )
    .values(
      **updates,
      review_revision=DocumentRecord.review_revision + 1,
    )
    .execution_options(synchronize_session=False)
  )
  try:
    result = session.execute(statement)
  except Exception:
    _rollback_once(session)
    raise

  if result.rowcount != 1:
    _rollback_once(session)
    raise StaleReviewWriteError(
      "The document review changed before this action could be saved."
    )

  try:
    session.commit()
  except Exception:
    _rollback_once(session)
    raise
  session.refresh(record)
  return record


def _rollback_once(session: Session) -> None:
  """Attempt one rollback without replacing the authoritative failure."""
  try:
    session.rollback()
  except Exception:  # noqa: BLE001 - preserve execute/commit/stale failure
    pass
