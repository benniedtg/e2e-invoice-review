from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from app.correction_email import (
  CorrectionEmailDraft,
  CorrectionEmailDrafter,
  CorrectionEmailDraftingError,
)
from app.invoices import ValidationIssue
from app.providers.azure_openai import AzureOpenAIError, AzureOpenAIProvider
from app.schemas import InvoiceDocument, Money, NormalizedDocument, ReceiptDocument

CORRECTION_EMAIL_INSTRUCTIONS = """\
Draft a concise, professional correction request from Maya, Finance Administration,
Northstar Facilities B.V., to the supplier or merchant. Ask for a corrected document or
clarification and use only the supplied top-level document values and issue details.

Do not mention AI, extraction confidence, provider provenance, or any internal system. Do not
invent facts, people, or email addresses. Do not claim to send, queue, store, or persist the
draft or perform any of those actions. Return only the strict recipient_name, subject, and body
fields required by the output schema.

Sanitized JSON payload:
"""

_INVOICE_FIELDS = (
  "vendor_name",
  "vendor_vat_id",
  "customer_name",
  "customer_vat_id",
  "invoice_number",
  "invoice_date",
  "due_date",
  "purchase_order",
  "currency",
  "subtotal",
  "total_discount",
  "total_tax",
  "invoice_total",
)
_RECEIPT_FIELDS = (
  "merchant_name",
  "transaction_date",
  "currency",
  "subtotal",
  "total_tax",
  "total",
  "tip",
)


class AzureOpenAICorrectionEmailDrafter(CorrectionEmailDrafter):
  """Generate one strict draft from a minimized normalized-document payload."""

  def __init__(self, provider: AzureOpenAIProvider) -> None:
    self._provider = provider

  def draft(
    self,
    document: NormalizedDocument,
    issues: tuple[ValidationIssue, ...],
  ) -> CorrectionEmailDraft:
    """Draft from already-filtered issues without re-running business policy."""
    prompt = CORRECTION_EMAIL_INSTRUCTIONS + json.dumps(
      {
        "document": _document_payload(document),
        "issues": [_issue_payload(issue) for issue in issues],
      },
      ensure_ascii=False,
      separators=(",", ":"),
    )
    try:
      return self._provider.generate_structured(
        prompt=prompt,
        output_type=CorrectionEmailDraft,
      )
    except AzureOpenAIError:
      raise CorrectionEmailDraftingError(
        "Azure OpenAI could not draft the correction email."
      ) from None


def _document_payload(document: NormalizedDocument) -> dict[str, object]:
  """Serialize only effective policy-relevant top-level field values."""
  if isinstance(document, InvoiceDocument):
    field_names = _INVOICE_FIELDS
  elif isinstance(document, ReceiptDocument):
    field_names = _RECEIPT_FIELDS
  else:
    raise TypeError("Correction-email drafting requires an invoice or receipt.")

  payload: dict[str, object] = {"document_type": document.document_type.value}
  payload.update({
    name: _json_value(getattr(document, name).value)
    for name in field_names
    if getattr(document, name) is not None
  })
  return payload


def _issue_payload(issue: ValidationIssue) -> dict[str, object]:
  """Serialize only issue facts approved for the correction request."""
  return {
    "code": issue.code.value,
    "field": issue.field,
    "message": issue.message,
    "expected": _json_value(issue.expected),
    "actual": _json_value(issue.actual),
  }


def _json_value(value: object) -> object:
  """Convert known effective scalar values to deterministic JSON-safe data."""
  if isinstance(value, Money):
    return value.model_dump(mode="json")
  if isinstance(value, date):
    return value.isoformat()
  if isinstance(value, Decimal):
    return str(value)
  return value
