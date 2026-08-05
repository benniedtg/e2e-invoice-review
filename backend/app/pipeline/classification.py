from __future__ import annotations

import json
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.accounting import GENERAL_LEDGER_CATALOG, resolve_general_ledger_account
from app.providers.azure_openai import AzureOpenAIProvider
from app.schemas import InvoiceDocument, NormalizedDocument, ReceiptDocument

SUPPORTED_DOCUMENT_MIME_TYPES = frozenset(
  {
    "application/pdf",
    "image/jpeg",
    "image/png",
  }
)

CLASSIFICATION_INSTRUCTIONS = """\
Classify the attached financial document into exactly one category:
- invoice: a document requesting payment from a customer.
- receipt: evidence that a purchase or expense has already been paid.
- other: the document is not clearly an invoice or a receipt.

When uncertain, use other instead of guessing. Give one short reason based on the
document type, without repeating names, identifiers, totals, or other sensitive values.
"""

GENERAL_LEDGER_INSTRUCTIONS = """\
Choose exactly one Northstar general-ledger account for the normalized financial
document in the JSON payload below. Use the fixed catalog supplied in that payload.
Base the choice only on the supplied vendor or merchant identity, receipt expense
category when present, and item descriptions or product codes. Return a short,
plain-English reason without repeating names, identifiers, or amounts.

JSON payload:
"""


class ClassificationType(StrEnum):
  """Document categories used to select the next pipeline step."""

  INVOICE = "invoice"
  RECEIPT = "receipt"
  OTHER = "other"


class DocumentClassification(BaseModel):
  """Provider-independent document classification result."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  document_type: ClassificationType
  reason: str = Field(min_length=1, max_length=200)


class DocumentClassifier:
  """Classify a document before selecting its extraction pipeline."""

  def __init__(self, provider: AzureOpenAIProvider) -> None:
    self._provider = provider

  def classify(
    self,
    document_bytes: bytes,
    mime_type: str,
  ) -> DocumentClassification:
    """Return invoice, receipt, or other for one PDF or image."""
    if not document_bytes:
      raise ValueError("Document bytes cannot be empty.")

    normalized_mime_type = mime_type.strip().lower()
    if normalized_mime_type not in SUPPORTED_DOCUMENT_MIME_TYPES:
      raise ValueError(
        "Document MIME type must be application/pdf, image/png, or image/jpeg."
      )

    return self._provider.analyze_document(
      document_bytes=document_bytes,
      mime_type=normalized_mime_type,
      instructions=CLASSIFICATION_INSTRUCTIONS,
      output_type=DocumentClassification,
    )


class GeneralLedgerClassification(BaseModel):
  """A locally validated Northstar GL suggestion for a normalized document."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  account_code: str = Field(pattern=r"^\d{4}$")
  account_name: str = Field(min_length=1, max_length=100)
  reason: str = Field(min_length=1, max_length=200)

  @model_validator(mode="after")
  def validate_canonical_account(self) -> GeneralLedgerClassification:
    """Prevent callers from pairing a catalog code with a non-canonical name."""
    account = resolve_general_ledger_account(self.account_code)
    if self.account_name != account.name:
      raise ValueError("GL account name must match the fixed catalog.")
    return self


class _GeneralLedgerModelOutput(BaseModel):
  """The minimal strict shape accepted from the model before local resolution."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  account_code: str = Field(pattern=r"^\d{4}$")
  reason: str = Field(min_length=1, max_length=200)


class StructuredOutputGenerator(Protocol):
  """Provider contract for strict structured generation from text or JSON input."""

  def generate_structured[StructuredOutput: BaseModel](
    self,
    *,
    prompt: str,
    output_type: type[StructuredOutput],
  ) -> StructuredOutput:
    """Generate a strict provider-independent Pydantic result."""
    ...


class GeneralLedgerClassifier:
  """Suggest and locally validate one Northstar GL account for a document."""

  def __init__(self, provider: StructuredOutputGenerator) -> None:
    self._provider = provider

  def classify(self, document: NormalizedDocument) -> GeneralLedgerClassification:
    """Classify normalized invoice or receipt data without sending source bytes."""
    output = self._provider.generate_structured(
      prompt=_general_ledger_prompt(document),
      output_type=_GeneralLedgerModelOutput,
    )
    account = resolve_general_ledger_account(output.account_code)
    return GeneralLedgerClassification(
      account_code=account.code,
      account_name=account.name,
      reason=output.reason,
    )


def _general_ledger_prompt(document: NormalizedDocument) -> str:
  """Serialize the smallest useful normalized document view for GL selection."""
  payload = {
    "catalog": [
      {"code": account.code, "name": account.name}
      for account in GENERAL_LEDGER_CATALOG
    ],
    "document": _general_ledger_document_payload(document),
  }
  return GENERAL_LEDGER_INSTRUCTIONS + json.dumps(
    payload,
    ensure_ascii=False,
    separators=(",", ":"),
  )


def _general_ledger_document_payload(document: NormalizedDocument) -> dict[str, object]:
  """Keep only identity and line-item details permitted for GL suggestion."""
  if isinstance(document, InvoiceDocument):
    return {
      "document_type": "invoice",
      "vendor": _compact({"name": _field_value(document.vendor_name)}),
      "items": _invoice_items(document),
    }

  if isinstance(document, ReceiptDocument):
    return {
      "document_type": "receipt",
      "merchant": _compact({"name": _field_value(document.merchant_name)}),
      "expense_category": _field_value(document.expense_category),
      "items": _receipt_items(document),
    }

  raise TypeError("GL classification requires a normalized invoice or receipt.")


def _invoice_items(document: InvoiceDocument) -> list[dict[str, str]]:
  return [
    _compact(
      {
        "description": _field_value(item.description),
        "product_code": _field_value(item.product_code),
      }
    )
    for item in document.items
    if item.description is not None or item.product_code is not None
  ]


def _receipt_items(document: ReceiptDocument) -> list[dict[str, str]]:
  return [
    _compact(
      {
        "description": _field_value(item.description),
        "product_code": _field_value(item.product_code),
      }
    )
    for item in document.items
    if item.description is not None or item.product_code is not None
  ]


def _field_value(field: object) -> str | None:
  value = getattr(field, "value", None)
  return value if isinstance(value, str) else None


def _compact(values: dict[str, str | None]) -> dict[str, str]:
  return {key: value for key, value in values.items() if value is not None}
