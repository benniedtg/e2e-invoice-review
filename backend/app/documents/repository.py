from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import (
  ColumnElement,
  ColumnExpressionArgument,
  exists,
  func,
  null,
  select,
  update,
)
from sqlalchemy.orm import Session

from app.assistant.schemas import DocumentGroupTotal, DocumentQuery, QueryGroup
from app.documents.keys import DocumentFacts, DocumentIdentity, normalize_name, to_cents
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


def search_documents(
  session: Session,
  query: DocumentQuery,
  limit: int,
) -> tuple[Sequence[DocumentRecord], int]:
  """Return up to limit matching documents, newest first, and how many match in all."""
  conditions = _query_conditions(query)
  match_count = session.scalar(
    select(func.count()).select_from(DocumentRecord).where(*conditions)
  )
  statement = (
    select(DocumentRecord)
    .where(*conditions)
    .order_by(DocumentRecord.document_date.desc(), DocumentRecord.created_at.desc())
    .limit(limit)
  )
  return session.scalars(statement).all(), match_count or 0


def total_documents(
  session: Session,
  query: DocumentQuery,
) -> tuple[DocumentGroupTotal, ...]:
  """Count and sum every matching document per requested group and currency."""
  group = _group_column(query.group_by)
  statement = (
    select(
      group,
      DocumentRecord.currency,
      func.count(),
      func.sum(DocumentRecord.total_cents),
      func.count(DocumentRecord.total_cents),
    )
    .where(*_query_conditions(query))
    .group_by(group, DocumentRecord.currency)
    .order_by(group, DocumentRecord.currency)
  )
  return tuple(
    DocumentGroupTotal(
      group=group_key,
      currency=currency,
      document_count=document_count,
      total_cents=total_cents,
      documents_without_total=document_count - counted_totals,
    )
    for group_key, currency, document_count, total_cents, counted_totals in session.execute(
      statement
    )
  )


def save_corrections(
  session: Session,
  record: DocumentRecord,
  *,
  expected_revision: int,
  field_overrides: dict[str, object],
  validation: ValidationReport,
  identity: DocumentIdentity,
  facts: DocumentFacts,
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
      **asdict(facts),
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


def _query_conditions(query: DocumentQuery) -> list[ColumnElement[bool]]:
  """Translate one validated typed query into bound SQL conditions that must all hold."""
  conditions: list[ColumnElement[bool]] = []
  if query.statuses:
    conditions.append(
      DocumentRecord.status.in_([status.value for status in query.statuses])
    )
  if query.document_types:
    conditions.append(
      DocumentRecord.document_type.in_([kind.value for kind in query.document_types])
    )
  vendor = normalize_name(query.vendor_text or "")
  if vendor:
    conditions.append(DocumentRecord.vendor_search_key.contains(vendor, autoescape=True))
  if query.date_from is not None:
    conditions.append(DocumentRecord.document_date >= query.date_from)
  if query.date_to is not None:
    conditions.append(DocumentRecord.document_date <= query.date_to)
  if query.gl_account_codes:
    conditions.append(_effective_gl_code().in_(query.gl_account_codes))
  if query.min_total is not None:
    conditions.append(DocumentRecord.total_cents >= to_cents(query.min_total))
  if query.max_total is not None:
    conditions.append(DocumentRecord.total_cents <= to_cents(query.max_total))
  if query.has_errors is not None:
    # SQLite's json_extract returns a JSON boolean as 1 or 0.
    is_valid = func.json_extract(DocumentRecord.validation, "$.is_valid")
    conditions.append(is_valid == (0 if query.has_errors else 1))
  if query.issue_codes:
    issue = func.json_each(DocumentRecord.validation, "$.issues").table_valued("value")
    codes = [code.value for code in query.issue_codes]
    conditions.append(
      exists().select_from(issue).where(func.json_extract(issue.c.value, "$.code").in_(codes))
    )
  if query.is_duplicate is not None:
    conditions.append(
      DocumentRecord.duplicate_of_id.is_not(None)
      if query.is_duplicate
      else DocumentRecord.duplicate_of_id.is_(None)
    )
  if query.used_llm_fallback is not None:
    fallback_count = func.json_array_length(
      DocumentRecord.reconciliation,
      "$.fallback_fields",
    )
    conditions.append(fallback_count > 0 if query.used_llm_fallback else fallback_count == 0)
  return conditions


def _effective_gl_code() -> ColumnElement[str | None]:
  """The reviewer's saved account, or the model suggestion while none is saved."""
  return func.coalesce(
    DocumentRecord.selected_gl_code,
    func.json_extract(DocumentRecord.gl_suggestion, "$.account_code"),
  )


def _group_column(group_by: QueryGroup) -> ColumnExpressionArgument[str | None]:
  """Pick the stored value counts and totals are broken down by."""
  if group_by == QueryGroup.GL_ACCOUNT:
    return _effective_gl_code()
  if group_by == QueryGroup.VENDOR:
    return DocumentRecord.vendor_name
  if group_by == QueryGroup.STATUS:
    return DocumentRecord.status
  if group_by == QueryGroup.DOCUMENT_TYPE:
    return DocumentRecord.document_type
  return null()
