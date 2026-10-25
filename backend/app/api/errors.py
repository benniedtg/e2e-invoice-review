from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.accounting import GeneralLedgerCatalogError
from app.assistant import AssistantOutputError
from app.config import ConfigurationError
from app.correction_email import CorrectionEmailDraftingError
from app.document_review import InvalidCorrectionError
from app.documents.repository import DocumentNotFoundError
from app.pipeline import PipelineStateError
from app.providers import AzureOpenAIError, DocumentIntelligenceError
from app.service import ReviewConflictError, ReviewInputError


class ErrorCode(StrEnum):
  """Stable failure identifiers the review interface can branch on."""

  PAYLOAD_TOO_LARGE = "payload_too_large"
  UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
  EMPTY_DOCUMENT = "empty_document"
  DOCUMENT_NOT_FOUND = "document_not_found"
  INVALID_REQUEST = "invalid_request"
  REVIEW_CONFLICT = "review_conflict"
  INVALID_REVIEW_INPUT = "invalid_review_input"
  CONFIGURATION_ERROR = "configuration_error"
  PROVIDER_ERROR = "provider_error"
  INVALID_GL_SUGGESTION = "invalid_gl_suggestion"
  INVALID_ASSISTANT_OUTPUT = "invalid_assistant_output"
  PIPELINE_ERROR = "pipeline_error"
  INTERNAL_ERROR = "internal_error"


UNEXPECTED_MESSAGE = "Unexpected server error."
"""Fixed text for any failure whose detail must not reach the client."""


class ErrorDetail(BaseModel):
  """One safe user-facing failure."""

  code: ErrorCode
  message: str


class ErrorBody(BaseModel):
  """The envelope returned by every failing endpoint."""

  error: ErrorDetail


class RequestError(Exception):
  """A request rejected locally before any provider call."""

  def __init__(self, code: ErrorCode, message: str, status_code: int) -> None:
    super().__init__(message)
    self.code = code
    self.status_code = status_code


def error_response(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
  """Serialize one typed error envelope."""
  body = ErrorBody(error=ErrorDetail(code=code, message=message))
  return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def classify_exception(exc: Exception) -> tuple[ErrorDetail, int]:
  """Decide the safe envelope and status for one raised failure.

  Both the registered handlers and the streaming route use this, so a failure
  reported inside a started stream cannot drift from the same failure reported
  as an HTTP status.
  """
  if isinstance(exc, RequestError):
    return ErrorDetail(code=exc.code, message=str(exc)), exc.status_code

  if isinstance(exc, RequestValidationError):
    return ErrorDetail(
      code=ErrorCode.INVALID_REQUEST,
      message="Request body is invalid.",
    ), 422

  if isinstance(exc, InvalidCorrectionError):
    return ErrorDetail(code=ErrorCode.INVALID_REQUEST, message=str(exc)), 422

  if isinstance(exc, ReviewConflictError):
    return ErrorDetail(code=ErrorCode.REVIEW_CONFLICT, message=str(exc)), 409

  if isinstance(exc, ReviewInputError):
    return ErrorDetail(code=ErrorCode.INVALID_REVIEW_INPUT, message=str(exc)), 400

  if isinstance(exc, ConfigurationError):
    return ErrorDetail(code=ErrorCode.CONFIGURATION_ERROR, message=str(exc)), 503

  if isinstance(
    exc,
    AzureOpenAIError | CorrectionEmailDraftingError | DocumentIntelligenceError,
  ):
    return ErrorDetail(code=ErrorCode.PROVIDER_ERROR, message=str(exc)), 502

  if isinstance(exc, GeneralLedgerCatalogError):
    return ErrorDetail(code=ErrorCode.INVALID_GL_SUGGESTION, message=str(exc)), 502

  if isinstance(exc, AssistantOutputError):
    return ErrorDetail(code=ErrorCode.INVALID_ASSISTANT_OUTPUT, message=str(exc)), 502

  if isinstance(exc, DocumentNotFoundError):
    return ErrorDetail(code=ErrorCode.DOCUMENT_NOT_FOUND, message=str(exc)), 404

  # Driver detail is never exposed, so database failures keep fixed text.
  if isinstance(exc, SQLAlchemyError):
    return ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=UNEXPECTED_MESSAGE), 500

  if isinstance(exc, PipelineStateError):
    return ErrorDetail(code=ErrorCode.PIPELINE_ERROR, message=str(exc)), 500

  if isinstance(exc, ValidationError):
    detail = ErrorDetail(
      code=ErrorCode.PIPELINE_ERROR,
      message="Provider or pipeline output could not be normalized.",
    )
    return detail, 500

  return ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=UNEXPECTED_MESSAGE), 500


def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
  """Serialize one classified failure as the typed error envelope."""
  detail, status_code = classify_exception(exc)
  body = ErrorBody(error=detail)
  return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
  """Route every expected domain failure through the shared classifier."""
  for exception_type in (
    RequestError,
    RequestValidationError,
    InvalidCorrectionError,
    ReviewConflictError,
    ReviewInputError,
    ConfigurationError,
    AzureOpenAIError,
    CorrectionEmailDraftingError,
    DocumentIntelligenceError,
    GeneralLedgerCatalogError,
    AssistantOutputError,
    DocumentNotFoundError,
    SQLAlchemyError,
    PipelineStateError,
    ValidationError,
    Exception,
  ):
    app.add_exception_handler(exception_type, _handle_exception)
