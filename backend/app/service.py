from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from hashlib import sha256 as build_sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.accounting import GeneralLedgerCatalogError, resolve_general_ledger_account
from app.assistant import (
  AssistantAnswer,
  DocumentAssistant,
  DocumentGroupTotal,
  DocumentQuery,
  QueryAggregate,
  QueryIntent,
)
from app.config import (
  NORTHSTAR_POLICY,
  load_azure_openai_settings,
  load_document_intelligence_settings,
)
from app.correction_email import (
  CorrectionEmailDraft,
  CorrectionEmailDrafter,
  supplier_fixable_issues,
)
from app.document_review import (
  DocumentCorrections,
  apply_field_overrides,
  document_field_name,
)
from app.documents import repository, storage
from app.documents.keys import DocumentIdentity, document_facts, document_identity
from app.documents.models import DocumentRecord, ReviewStatus
from app.invoices import (
  ValidationContext,
  ValidationIssue,
  ValidationIssueCode,
  ValidationReport,
  ValidationSeverity,
  build_duplicate_issue,
  validate_document,
  with_issues,
)
from app.pipeline import (
  GeneralLedgerClassifier,
  Pipeline,
  PipelineResult,
  PipelineStatus,
  StepObserver,
  StepPhase,
  build_document_pipeline,
)
from app.providers import (
  AzureDocumentIntelligenceProvider,
  AzureOpenAICorrectionEmailDrafter,
  AzureOpenAIDocumentReviewer,
  AzureOpenAIProvider,
)
from app.schemas import InvoiceDocument, Money, NormalizedDocument, ReceiptDocument


class ReviewConflictError(Exception):
  """The stored review state does not permit the requested mutation."""


class ReviewInputError(ValueError):
  """A human review value is outside the local business catalog."""


@dataclass(frozen=True, slots=True)
class StoredDocumentFile:
  """Server-resolved source file metadata safe for an inline response."""

  path: Path
  media_type: str
  filename: str


@dataclass(frozen=True, slots=True)
class DocumentAnswer:
  """One answer with the typed filter and the stored evidence behind it."""

  answer: AssistantAnswer
  query: DocumentQuery
  match_count: int
  documents: Sequence[DocumentRecord]
  groups: tuple[DocumentGroupTotal, ...]


ANSWER_DOCUMENT_LIMIT = 20
"""Documents an answer may draw on; counts and totals still cover every match."""

UNSUPPORTED_ANSWER = (
  "I can only answer questions about the stored invoice and receipt reviews."
)
NO_MATCH_ANSWER = "No stored documents match this question."


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
  """Build the configured pipeline once and reuse it for every request."""
  openai_provider = AzureOpenAIProvider(load_azure_openai_settings())
  return build_document_pipeline(
    AzureOpenAIDocumentReviewer(openai_provider),
    AzureDocumentIntelligenceProvider(load_document_intelligence_settings()),
    GeneralLedgerClassifier(openai_provider),
    NORTHSTAR_POLICY,
  )


@lru_cache(maxsize=1)
def get_correction_email_drafter() -> CorrectionEmailDrafter:
  """Build and cache the optional strict correction-email operation."""
  provider = AzureOpenAIProvider(load_azure_openai_settings())
  return AzureOpenAICorrectionEmailDrafter(provider)


@lru_cache(maxsize=1)
def get_document_assistant() -> DocumentAssistant:
  """Build and cache the review-history question operation."""
  return DocumentAssistant(AzureOpenAIProvider(load_azure_openai_settings()))


STORAGE_STEP_ID = "storage"
"""Identifies hashing, duplicate detection, and persistence to observers."""


def process_document(
  session: Session,
  document_bytes: bytes,
  mime_type: str,
  original_filename: str,
  on_step: StepObserver | None = None,
) -> DocumentRecord:
  """Process one document, flag duplicates, and store the result."""
  result = get_pipeline().run(document_bytes, mime_type, on_step)
  if on_step is not None:
    on_step(STORAGE_STEP_ID, StepPhase.STARTED)

  identity = document_identity(result.document)
  content_hash = build_sha256(document_bytes).hexdigest()

  duplicate, duplicate_code = _find_duplicate(session, content_hash, identity)
  validation = _validation_with_duplicate(result.validation, duplicate_code)

  record = DocumentRecord(
    id=str(uuid4()),
    created_at=datetime.now(UTC),
    original_filename=original_filename,
    content_type=mime_type,
    size_bytes=len(document_bytes),
    sha256=content_hash,
    status=ReviewStatus.PENDING,
    pipeline_status=result.status.value,
    classification=result.classification.model_dump(mode="json"),
    extraction=_dump(result.primary_document),
    independent_review=_dump(result.independent_review),
    reconciliation=_dump(result.reconciliation),
    merged_document=_dump(result.document),
    gl_suggestion=_dump(result.general_ledger),
    validation=_dump(validation),
    document_type=result.document.document_type.value if result.document else None,
    vendor_name=identity.vendor_name,
    invoice_number=identity.invoice_number,
    vendor_name_key=identity.vendor_name_key,
    invoice_number_key=identity.invoice_number_key,
    **asdict(document_facts(result.document)),
    duplicate_of_id=duplicate.id if duplicate is not None else None,
    field_overrides={},
  )

  storage.save_document(record.id, document_bytes, mime_type)
  stored = repository.create_document(session, record)
  if on_step is not None:
    on_step(STORAGE_STEP_ID, StepPhase.COMPLETED)
  return stored


def list_documents(session: Session) -> Sequence[DocumentRecord]:
  """Return the review history, newest first."""
  return repository.list_documents(session)


def get_document(session: Session, document_id: str) -> DocumentRecord:
  """Return one stored document."""
  return repository.get_document(session, document_id)


def correct_document(
  session: Session,
  document_id: str,
  corrections: DocumentCorrections,
) -> DocumentRecord:
  """Apply one explicit correction patch and atomically revalidate the result."""
  record, result = _pending_financial_record(
    session,
    document_id,
    action="corrected",
  )
  baseline = _immutable_merged_document(record, result.document)

  combined = dict(record.field_overrides)
  combined.update(corrections.model_dump(exclude_unset=True))
  normalized = DocumentCorrections.model_validate(combined).model_dump(
    exclude_unset=True,
  )
  apply_field_overrides(baseline, normalized)
  overrides = {
    name: value
    for name, value in normalized.items()
    if value != _baseline_value(baseline, name)
  }
  effective = apply_field_overrides(baseline, overrides)
  identity = document_identity(effective)
  duplicate, duplicate_code = _find_duplicate(
    session,
    record.sha256,
    identity,
    exclude_id=record.id,
  )
  human_fields = frozenset(document_field_name(name) for name in overrides)
  validation = validate_document(effective, ValidationContext(
    policy=NORTHSTAR_POLICY,
    duplicate_code=duplicate_code,
    human_fields=human_fields,
  ))
  serialized_overrides = DocumentCorrections.model_validate(overrides).model_dump(
    exclude_unset=True,
    mode="json",
  )

  try:
    return repository.save_corrections(
      session,
      record,
      expected_revision=record.review_revision,
      field_overrides=serialized_overrides,
      validation=validation,
      identity=identity,
      facts=document_facts(effective),
      duplicate_of_id=duplicate.id if duplicate is not None else None,
    )
  except repository.StaleReviewWriteError as exc:
    raise ReviewConflictError(str(exc)) from None


def select_gl_account(
  session: Session,
  document_id: str,
  account_code: str,
) -> DocumentRecord:
  """Store one explicit locally validated human GL selection."""
  record, _ = _pending_financial_record(session, document_id)
  try:
    resolve_general_ledger_account(account_code)
  except GeneralLedgerCatalogError:
    raise ReviewInputError(
      "Selected GL account is not in the Northstar catalog."
    ) from None
  try:
    return repository.select_gl_code(
      session,
      record,
      account_code,
      record.review_revision,
    )
  except repository.StaleReviewWriteError as exc:
    raise ReviewConflictError(str(exc)) from None


def decide_document(
  session: Session,
  document_id: str,
  decision: ReviewStatus,
) -> DocumentRecord:
  """Approve or reject one pending financial review after local gates."""
  record, result = _pending_financial_record(session, document_id)
  if decision not in {ReviewStatus.APPROVED, ReviewStatus.REJECTED}:
    raise ReviewInputError("Decision must be approved or rejected.")

  if decision == ReviewStatus.APPROVED:
    if result.validation is None or any(
      issue.severity == ValidationSeverity.ERROR
      for issue in result.validation.issues
    ):
      raise ReviewConflictError(
        "Resolve all validation errors before approval."
      )
    if record.selected_gl_code is None:
      raise ReviewConflictError(
        "Select a valid GL account before approval."
      )
    try:
      resolve_general_ledger_account(record.selected_gl_code)
    except GeneralLedgerCatalogError:
      raise ReviewConflictError(
        "Select a valid GL account before approval."
      ) from None

  try:
    return repository.set_review_decision(
      session,
      record,
      decision,
      datetime.now(UTC),
      record.review_revision,
    )
  except repository.StaleReviewWriteError as exc:
    raise ReviewConflictError(str(exc)) from None


def stored_document_file(
  session: Session,
  document_id: str,
) -> StoredDocumentFile:
  """Resolve one source path entirely from trusted stored record values."""
  record = get_document(session, document_id)
  return StoredDocumentFile(
    path=storage.document_path(record.id, record.content_type),
    media_type=record.content_type,
    filename=record.original_filename,
  )


def draft_correction_email(
  session: Session,
  document_id: str,
) -> CorrectionEmailDraft:
  """Draft one supplier correction request without persisting or sending it."""
  record = repository.get_document(session, document_id)
  if record.status not in {ReviewStatus.PENDING, ReviewStatus.REJECTED}:
    raise ReviewConflictError(
      "Correction emails are available only for pending or rejected documents."
    )
  if record.pipeline_status != PipelineStatus.COMPLETED or any(
    artifact is None
    for artifact in (
      record.extraction,
      record.independent_review,
      record.reconciliation,
      record.merged_document,
      record.gl_suggestion,
      record.validation,
    )
  ):
    raise ReviewConflictError(
      "Correction emails require a completed financial document."
    )

  try:
    result = record.to_pipeline_result()
  except (TypeError, ValueError):
    raise ReviewConflictError(
      "Correction emails require a completed financial document."
    ) from None
  if result.document is None or result.validation is None:
    raise ReviewConflictError(
      "Correction emails require a completed financial document."
    )

  issues = supplier_fixable_issues(result.validation.issues)
  if not issues:
    raise ReviewConflictError(
      "This document has no supplier-fixable issues."
    )
  return get_correction_email_drafter().draft(result.document, issues)


def ask_documents(session: Session, question: str) -> DocumentAnswer:
  """Plan a typed filter, retrieve stored reviews, and answer only from them."""
  assistant = get_document_assistant()
  query = assistant.plan(question, date.today())
  if query.intent == QueryIntent.UNSUPPORTED:
    return DocumentAnswer(
      answer=AssistantAnswer(answer=UNSUPPORTED_ANSWER),
      query=query,
      match_count=0,
      documents=(),
      groups=(),
    )

  documents, match_count = repository.search_documents(
    session,
    query,
    ANSWER_DOCUMENT_LIMIT,
  )
  groups = (
    ()
    if query.aggregate == QueryAggregate.LIST
    else repository.total_documents(session, query)
  )
  # Nothing to ground an answer in, so the model is not asked to write one.
  answer = (
    AssistantAnswer(answer=NO_MATCH_ANSWER)
    if match_count == 0
    else assistant.answer(question, query, documents, match_count, groups)
  )
  return DocumentAnswer(
    answer=answer,
    query=query,
    match_count=match_count,
    documents=documents,
    groups=groups,
  )


def delete_document(session: Session, document_id: str) -> None:
  """Delete one row and exact source with recoverable cross-resource staging."""
  try:
    record = repository.get_document(session, document_id)
  except repository.DocumentNotFoundError:
    pending = storage.pending_document_deletion(document_id)
    if pending is None:
      raise
    storage.finish_document_deletion(pending)
    return

  snapshot = repository.snapshot_document(record)
  staged = storage.stage_document_deletion(record.id, record.content_type)
  try:
    repository.delete_document(session, record.id)
  except Exception:
    try:
      storage.restore_document_deletion(staged)
    except Exception:  # noqa: BLE001 - row still tracks the retryable tombstone
      pass
    raise

  try:
    storage.finish_document_deletion(staged)
  except Exception as cleanup_error:
    try:
      repository.restore_deleted_document(session, snapshot)
    except Exception as compensation_error:
      cleanup_error.add_note(
        "Document row compensation failed; the controlled tombstone remains "
        "retryable by canonical document ID."
      )
      raise cleanup_error from compensation_error
    try:
      storage.restore_document_deletion(staged)
    except Exception:  # noqa: BLE001 - restored row makes tombstone retryable
      pass
    raise


def _pending_financial_record(
  session: Session,
  document_id: str,
  action: str = "changed",
) -> tuple[DocumentRecord, PipelineResult]:
  """Require one mutable pending record with every completed artifact."""
  record = repository.get_document(session, document_id)
  if record.status != ReviewStatus.PENDING:
    raise ReviewConflictError(f"Only pending documents can be {action}.")
  if record.pipeline_status != PipelineStatus.COMPLETED or any(
    artifact is None
    for artifact in (
      record.extraction,
      record.independent_review,
      record.reconciliation,
      record.merged_document,
      record.gl_suggestion,
      record.validation,
    )
  ):
    raise ReviewConflictError(
      f"Only completed financial documents can be {action}."
    )
  result = record.to_pipeline_result()
  if (
    result.document is None
    or result.reconciliation is None
    or result.validation is None
  ):
    raise ReviewConflictError(
      f"Only completed financial documents can be {action}."
    )
  return record, result


def _find_duplicate(
  session: Session,
  content_hash: str,
  identity: DocumentIdentity,
  exclude_id: str | None = None,
) -> tuple[DocumentRecord | None, ValidationIssueCode | None]:
  """Prefer an exact byte match, then fall back to the supplier key."""
  duplicate = repository.find_duplicate_by_content(
    session,
    content_hash,
    exclude_id,
  )
  if duplicate is not None:
    return duplicate, ValidationIssueCode.DUPLICATE_FILE_CONTENT

  if identity.vendor_name_key is None or identity.invoice_number_key is None:
    return None, None

  duplicate = repository.find_duplicate_by_key(
    session,
    identity.vendor_name_key,
    identity.invoice_number_key,
    exclude_id,
  )
  if duplicate is None:
    return None, None
  return duplicate, ValidationIssueCode.DUPLICATE_INVOICE


def _validation_with_duplicate(
  report: ValidationReport | None,
  code: ValidationIssueCode | None,
) -> ValidationReport | None:
  """Add the duplicate issue to a report that the pure rules produced."""
  if report is None or code is None:
    return report
  issues: tuple[ValidationIssue, ...] = (build_duplicate_issue(code),)
  return with_issues(report, issues)


def _dump(model: object | None) -> dict[str, object] | None:
  """Serialize one optional pipeline stage for its JSON column."""
  if model is None:
    return None
  return model.model_dump(mode="json")  # pyright: ignore[reportAttributeAccessIssue]


def _immutable_merged_document(
  record: DocumentRecord,
  effective: NormalizedDocument,
) -> NormalizedDocument:
  """Rebuild the persisted baseline using the already-validated document type."""
  if record.merged_document is None:
    raise ReviewConflictError(
      "Only completed financial documents can be corrected."
    )
  if isinstance(effective, InvoiceDocument):
    return InvoiceDocument.model_validate(record.merged_document)
  if isinstance(effective, ReceiptDocument):
    return ReceiptDocument.model_validate(record.merged_document)
  raise ReviewConflictError("Only completed financial documents can be corrected.")


def _baseline_value(document: NormalizedDocument, correction_name: str) -> object:
  """Project one immutable normalized field into the correction scalar shape."""
  field = getattr(document, document_field_name(correction_name))
  if field is None:
    return None
  value = field.value
  return value.amount if isinstance(value, Money) else value
