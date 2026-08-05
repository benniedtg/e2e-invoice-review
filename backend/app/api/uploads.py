from __future__ import annotations

from fastapi import UploadFile

from app.api.errors import ErrorCode, RequestError

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
"""The client brief's fixed 4 MB limit for one uploaded document."""

MULTIPART_OVERHEAD_ALLOWANCE = 8 * 1024
"""Headroom so multipart framing cannot reject an exactly-sized document."""

MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_ALLOWANCE

OVERSIZED_MESSAGE = "Document must be 4 MB or smaller."

_MIME_TYPES_BY_SIGNATURE: tuple[tuple[bytes, str], ...] = (
  (b"%PDF-", "application/pdf"),
  (b"\x89PNG\r\n\x1a\n", "image/png"),
  (b"\xff\xd8\xff", "image/jpeg"),
)


def detect_mime_type(document_bytes: bytes) -> str:
  """Return the supported MIME type implied by a document's leading bytes."""
  for signature, mime_type in _MIME_TYPES_BY_SIGNATURE:
    if document_bytes.startswith(signature):
      return mime_type
  raise RequestError(
    ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    "Document must be a PDF, PNG, or JPEG file.",
    415,
  )


def read_document(upload: UploadFile) -> tuple[bytes, str]:
  """Read one bounded upload and derive its type from content, not metadata."""
  document_bytes = upload.file.read(MAX_UPLOAD_BYTES + 1)
  if len(document_bytes) > MAX_UPLOAD_BYTES:
    raise RequestError(ErrorCode.PAYLOAD_TOO_LARGE, OVERSIZED_MESSAGE, 413)
  if not document_bytes:
    raise RequestError(ErrorCode.EMPTY_DOCUMENT, "Document file is empty.", 400)
  return document_bytes, detect_mime_type(document_bytes)
