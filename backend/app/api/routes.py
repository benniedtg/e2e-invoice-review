from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import Field
from sqlalchemy.orm import Session

from app.accounting import GENERAL_LEDGER_CATALOG
from app.api.errors import ErrorBody, classify_exception
from app.api.uploads import read_document
from app.correction_email import CorrectionEmailDraft, supplier_fixable_issues
from app.document_review import (
  DocumentCorrections,
  FieldSource,
  effective_field_sources,
)
from app.documents.database import get_session
from app.documents.models import DocumentRecord, ReviewStatus
from app.pipeline import PipelineResult, StepPhase
from app.schemas.common import StrictSchema
from app.service import (
  correct_document,
  decide_document,
  delete_document,
  draft_correction_email,
  get_document,
  list_documents,
  process_document,
  select_gl_account,
  stored_document_file,
)

router = APIRouter()

SessionDependency = Annotated[Session, Depends(get_session)]

STREAM_HEADERS = {"cache-control": "no-store", "x-accel-buffering": "no"}
"""Keep every intermediary from buffering the stream into one delivery."""


class HealthResponse(StrictSchema):
  """Liveness result served without configuration or provider access."""

  status: str


class GeneralLedgerAccountResponse(StrictSchema):
  """One selectable Northstar account exposed to the review interface."""

  code: str
  name: str


class GeneralLedgerSelectionRequest(StrictSchema):
  """One explicit selection from the fixed Northstar GL catalog."""

  account_code: str = Field(pattern=r"^\d{4}$")


class DecisionRequest(StrictSchema):
  """One final human review decision."""

  decision: Literal["approved", "rejected"]


class DocumentSummaryResponse(StrictSchema):
  """One history row, small enough to list without the full extraction."""

  id: str
  created_at: datetime
  original_filename: str
  status: str
  pipeline_status: str
  document_type: str | None
  vendor_name: str | None
  invoice_number: str | None
  duplicate_of_id: str | None
  is_valid: bool | None


class DocumentResponse(StrictSchema):
  """One stored document with its recomposed pipeline result."""

  id: str
  created_at: datetime
  original_filename: str
  content_type: str
  size_bytes: int
  status: str
  duplicate_of_id: str | None
  selected_gl_code: str | None
  field_overrides: dict[str, Any]
  field_sources: dict[str, FieldSource]
  reviewed_at: datetime | None
  supplier_action_required: bool
  result: PipelineResult


def _summary(record: DocumentRecord) -> DocumentSummaryResponse:
  """Build one history row without rebuilding the whole pipeline result."""
  validation: dict[str, Any] | None = record.validation
  return DocumentSummaryResponse(
    id=record.id,
    created_at=record.created_at,
    original_filename=record.original_filename,
    status=record.status,
    pipeline_status=record.pipeline_status,
    document_type=record.document_type,
    vendor_name=record.vendor_name,
    invoice_number=record.invoice_number,
    duplicate_of_id=record.duplicate_of_id,
    is_valid=validation.get("is_valid") if validation is not None else None,
  )


def _document(record: DocumentRecord) -> DocumentResponse:
  """Build one full record, re-applying the strict terminal-state rules."""
  result = record.to_pipeline_result()
  field_sources = (
    effective_field_sources(result.reconciliation, record.field_overrides)
    if result.reconciliation is not None
    else {}
  )
  return DocumentResponse(
    id=record.id,
    created_at=record.created_at,
    original_filename=record.original_filename,
    content_type=record.content_type,
    size_bytes=record.size_bytes,
    status=record.status,
    duplicate_of_id=record.duplicate_of_id,
    selected_gl_code=record.selected_gl_code,
    field_overrides=record.field_overrides,
    field_sources=field_sources,
    reviewed_at=record.reviewed_at,
    supplier_action_required=bool(
      result.validation
      and supplier_fixable_issues(result.validation.issues)
    ),
    result=result,
  )


@router.get("/health")
def read_health() -> HealthResponse:
  """Report that the API process is running."""
  return HealthResponse(status="ok")


@router.post("/api/documents/process")
def process_uploaded_document(
  session: SessionDependency,
  file: Annotated[UploadFile, File()],
) -> DocumentResponse:
  """Process, store, and return one uploaded invoice or receipt."""
  document_bytes, mime_type = read_document(file)
  record = process_document(
    session,
    document_bytes,
    mime_type,
    file.filename or "document",
  )
  return _document(record)


def _frame(event: str, data: dict[str, Any]) -> str:
  """Serialize one server-sent event frame."""
  return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _process_events(
  session: Session,
  document_bytes: bytes,
  mime_type: str,
  original_filename: str,
) -> AsyncIterator[str]:
  """Run one document in a worker thread and stream its progress."""
  queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
  loop = asyncio.get_running_loop()

  def on_step(step_id: str, phase: StepPhase) -> None:
    """Hand one step transition from the worker thread to the event loop."""
    event = ("step", {"id": step_id, "phase": phase.value})
    loop.call_soon_threadsafe(queue.put_nowait, event)

  def work() -> dict[str, Any]:
    """Process and serialize inside the thread that owns the connection."""
    record = process_document(
      session,
      document_bytes,
      mime_type,
      original_filename,
      on_step,
    )
    return _document(record).model_dump(mode="json")

  async def produce() -> None:
    """Queue exactly one terminal frame, whatever happens."""
    try:
      await queue.put(("result", await asyncio.to_thread(work)))
    except Exception as exc:  # noqa: BLE001 - every failure becomes an error frame
      detail, _ = classify_exception(exc)
      await queue.put(("error", ErrorBody(error=detail).model_dump(mode="json")))
    finally:
      await queue.put(None)

  worker = asyncio.create_task(produce())
  try:
    while (event := await queue.get()) is not None:
      yield _frame(*event)
  finally:
    await worker


@router.post("/api/documents/process/stream")
async def stream_processed_document(
  session: SessionDependency,
  file: Annotated[UploadFile, File()],
) -> StreamingResponse:
  """Process one uploaded document, reporting each stage as it happens."""
  document_bytes, mime_type = read_document(file)
  return StreamingResponse(
    _process_events(session, document_bytes, mime_type, file.filename or "document"),
    media_type="text/event-stream",
    headers=STREAM_HEADERS,
  )


@router.get("/api/documents")
def read_documents(session: SessionDependency) -> list[DocumentSummaryResponse]:
  """List the review history, newest first."""
  return [_summary(record) for record in list_documents(session)]


@router.get("/api/documents/{document_id}")
def read_document_record(
  session: SessionDependency,
  document_id: str,
) -> DocumentResponse:
  """Return one stored document."""
  return _document(get_document(session, document_id))


@router.patch("/api/documents/{document_id}/corrections")
def correct_document_fields(
  session: SessionDependency,
  document_id: str,
  corrections: DocumentCorrections,
) -> DocumentResponse:
  """Atomically save explicit human fields and return the revalidated review."""
  return _document(correct_document(session, document_id, corrections))


@router.put("/api/documents/{document_id}/gl-selection")
def select_document_gl_account(
  session: SessionDependency,
  document_id: str,
  selection: GeneralLedgerSelectionRequest,
) -> DocumentResponse:
  """Store an explicit locally validated GL account selection."""
  return _document(
    select_gl_account(session, document_id, selection.account_code)
  )


@router.post("/api/documents/{document_id}/decision")
def decide_document_review(
  session: SessionDependency,
  document_id: str,
  request: DecisionRequest,
) -> DocumentResponse:
  """Finalize one pending document as approved or rejected."""
  return _document(
    decide_document(session, document_id, ReviewStatus(request.decision))
  )


@router.post("/api/documents/{document_id}/correction-email")
def create_correction_email_draft(
  session: SessionDependency,
  document_id: str,
) -> CorrectionEmailDraft:
  """Generate one copyable correction request without storing or sending it."""
  return draft_correction_email(session, document_id)


@router.get("/api/documents/{document_id}/file")
def read_document_file(
  session: SessionDependency,
  document_id: str,
) -> FileResponse:
  """Serve the trusted stored source inline for review."""
  file = stored_document_file(session, document_id)
  return FileResponse(
    file.path,
    media_type=file.media_type,
    filename=file.filename,
    content_disposition_type="inline",
  )


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(session: SessionDependency, document_id: str) -> None:
  """Delete one stored document and its uploaded file."""
  delete_document(session, document_id)


@router.get("/api/gl-accounts")
def read_general_ledger_accounts() -> list[GeneralLedgerAccountResponse]:
  """List the fixed Northstar catalog a reviewer can select from."""
  return [
    GeneralLedgerAccountResponse(code=account.code, name=account.name)
    for account in GENERAL_LEDGER_CATALOG
  ]
