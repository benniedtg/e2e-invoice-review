"""HTTP boundary for student claim checks. Receipts are read in memory and never stored."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.errors import ErrorCode, RequestError
from app.api.uploads import read_document
from app.claims.catalog import DOCUMENTS_BY_ID, POLICY_DIRECTORY
from app.claims.schemas import (
  AssessmentState,
  ClaimAnswers,
  ClaimResponse,
  NextQuestion,
  ReceiptFacts,
  ReceiptIssue,
)
from app.claims.service import (
  assess_claim,
  extract_receipt,
  interpret_answer,
  policy_catalog,
  reassess_claim,
)
from app.documents.database import get_session
from app.schemas.common import StrictSchema

router = APIRouter()

SessionDependency = Annotated[Session, Depends(get_session)]


class ExtractResponse(StrictSchema):
  """Stage 1: printed facts and the problems found in them."""

  facts: ReceiptFacts
  issues: tuple[ReceiptIssue, ...]


class AssessRequest(StrictSchema):
  """The receipt facts and every answer the student has given so far."""

  facts: ReceiptFacts
  answers: ClaimAnswers


class ReassessRequest(StrictSchema):
  """A previous assessment returned with new answers, to decide again without the model."""

  facts: ReceiptFacts
  answers: ClaimAnswers
  state: AssessmentState


class InterpretRequest(StrictSchema):
  """A typed reply to one question."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  question: NextQuestion
  text: str = Field(min_length=1, max_length=300)


class InterpretResponse(StrictSchema):
  """The reply in the question's format, or null when it did not answer it."""

  value: str | None


@router.post("/api/claims/extract")
def extract_claim_receipt(file: Annotated[UploadFile, File()]) -> ExtractResponse:
  """Read one receipt in memory; the file is never written anywhere."""
  document_bytes, mime_type = read_document(file)
  facts, issues = extract_receipt(document_bytes, mime_type)
  return ExtractResponse(facts=facts, issues=issues)


@router.post("/api/claims/assess")
def assess_claim_receipt(session: SessionDependency, request: AssessRequest) -> ClaimResponse:
  """Ask the next needed question, or retrieve evidence and decide each line."""
  return assess_claim(session, request.facts, request.answers)


@router.post("/api/claims/reassess")
def reassess_claim_receipt(
  session: SessionDependency,
  request: ReassessRequest,
) -> ClaimResponse:
  """Decide again from a verified assessment after the student answers a question."""
  return reassess_claim(session, request.facts, request.answers, request.state)


@router.post("/api/claims/interpret")
def interpret_claim_answer(request: InterpretRequest) -> InterpretResponse:
  """Map a typed reply onto the question it answers."""
  return InterpretResponse(value=interpret_answer(request.question, request.text))


@router.get("/api/claims/policies")
def read_claim_policies(session: SessionDependency) -> list[dict[str, Any]]:
  """List the insurers, products, and policy editions the checker knows."""
  return policy_catalog(session)


@router.get("/api/policy/documents/{document_id}/file")
def read_policy_document(document_id: str) -> FileResponse:
  """Serve one catalog policy PDF inline so citations can open their page."""
  document = DOCUMENTS_BY_ID.get(document_id)
  path = POLICY_DIRECTORY / document.file_name if document is not None else None
  if path is None or not path.is_file():
    raise RequestError(
      ErrorCode.DOCUMENT_NOT_FOUND,
      "No loaded policy document exists for that identifier.",
      404,
    )
  return FileResponse(
    path,
    media_type="application/pdf",
    filename=path.name,
    content_disposition_type="inline",
  )
