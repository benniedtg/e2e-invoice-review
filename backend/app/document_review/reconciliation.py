from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.document_review.base import DocumentReviewError
from app.document_review.schemas import (
  ComparisonStatus,
  DocumentReconciliation,
  FieldComparison,
  FieldSource,
  IndependentDocumentReview,
  ReviewDocumentType,
)
from app.schemas import (
  DocumentType,
  ExtractedField,
  InvoiceDocument,
  Money,
  NormalizedDocument,
  ReceiptDocument,
)

type NormalizerKind = Literal["text", "identifier", "date", "decimal"]
type FieldDescriptor = tuple[str, str, str, NormalizerKind]
type FallbackValue = str | date | Decimal
type FallbackExtractedField = (
  ExtractedField[str] | ExtractedField[date] | ExtractedField[Money]
)

INVOICE_FIELDS: tuple[FieldDescriptor, ...] = (
  ("vendor_name", "vendor_name", "Supplier", "text"),
  ("vendor_vat_id", "vendor_vat_id", "Supplier VAT number", "identifier"),
  ("customer_name", "customer_name", "Customer", "text"),
  ("customer_vat_id", "customer_vat_id", "Customer VAT number", "identifier"),
  ("invoice_number", "invoice_number", "Invoice number", "identifier"),
  ("invoice_date", "invoice_date", "Invoice date", "date"),
  ("due_date", "due_date", "Due date", "date"),
  ("purchase_order", "purchase_order", "Purchase order", "identifier"),
  ("currency", "currency", "Currency", "identifier"),
  ("subtotal", "subtotal", "Subtotal", "decimal"),
  ("total_discount", "total_discount", "Total discount", "decimal"),
  ("total_tax", "total_tax", "VAT total", "decimal"),
  ("invoice_total", "invoice_total", "Invoice total", "decimal"),
  ("amount_due", "amount_due", "Amount due", "decimal"),
)

RECEIPT_FIELDS: tuple[FieldDescriptor, ...] = (
  ("merchant_name", "merchant_name", "Merchant", "text"),
  ("transaction_date", "transaction_date", "Transaction date", "date"),
  ("expense_category", "expense_category", "Expense category", "text"),
  ("currency", "currency", "Currency", "identifier"),
  ("subtotal", "subtotal", "Subtotal", "decimal"),
  ("total_tax", "total_tax", "VAT total", "decimal"),
  ("total", "receipt_total", "Receipt total", "decimal"),
  ("tip", "tip", "Tip", "decimal"),
)

def _text(value: str) -> str:
  return "".join(character for character in value.casefold() if character.isalnum())


def _identifier(value: str) -> str:
  return re.sub(r"[^A-Z0-9]", "", value.upper())


def _date(value: str) -> str:
  try:
    return date.fromisoformat(value).isoformat()
  except ValueError:
    return value.strip().casefold()


def _decimal(value: str) -> str:
  try:
    return str(Decimal(value.replace(",", ".")).normalize())
  except InvalidOperation:
    return value.strip().casefold()


NORMALIZERS: dict[NormalizerKind, Callable[[str], str]] = {
  "text": _text,
  "identifier": _identifier,
  "date": _date,
  "decimal": _decimal,
}


def _shown(value: object | None) -> str | None:
  if value is None:
    return None
  if isinstance(value, Money):
    return str(value.amount)
  if isinstance(value, date):
    return value.isoformat()
  shown = str(value).strip()
  return shown or None


def _primary_value(field: ExtractedField[object] | None) -> object | None:
  return field.value if field is not None else None


def _comparison_status(
  primary_value: object | None,
  independent_value: object | None,
  normalizer_kind: NormalizerKind,
) -> ComparisonStatus:
  primary_shown = _shown(primary_value)
  independent_shown = _shown(independent_value)
  if primary_shown is None and independent_shown is None:
    return ComparisonStatus.MISSING_IN_BOTH
  if independent_shown is None:
    return ComparisonStatus.MISSING_IN_LLM
  if primary_shown is None:
    return ComparisonStatus.MISSING_IN_DOCUMENT_INTELLIGENCE
  normalizer = NORMALIZERS[normalizer_kind]
  if normalizer(primary_shown) == normalizer(independent_shown):
    return ComparisonStatus.MATCH
  return ComparisonStatus.DIFFERENT


def _fallback_field(
  value: FallbackValue,
  merged_currency: str | None,
  normalizer_kind: NormalizerKind,
) -> FallbackExtractedField:
  if normalizer_kind == "decimal":
    return ExtractedField[Money](
      value=Money(amount=value, currency_code=merged_currency),
    )
  if normalizer_kind == "date":
    return ExtractedField[date](value=value)
  return ExtractedField[str](value=value)


def merge_document_extractions(
  primary: NormalizedDocument,
  independent: IndependentDocumentReview,
) -> tuple[NormalizedDocument, DocumentReconciliation]:
  """Fill DI-null scalar fields from an independent reading and retain DI evidence."""
  expected_type = ReviewDocumentType(primary.document_type.value)
  if independent.document_type != expected_type:
    raise DocumentReviewError(
      "Independent document type does not match the Document Intelligence extraction."
    )

  descriptors = (
    INVOICE_FIELDS if primary.document_type == DocumentType.INVOICE else RECEIPT_FIELDS
  )
  primary_currency = _primary_value(primary.currency)
  merged_currency = _shown(primary_currency) or _shown(independent.currency)
  updates: dict[str, FallbackExtractedField] = {}
  comparisons: list[FieldComparison] = []
  fallback_fields: list[str] = []
  conflict_fields: list[str] = []
  field_sources: dict[str, FieldSource] = {}

  for field, independent_field, label, normalizer_kind in descriptors:
    primary_field = getattr(primary, field)
    primary_value = _primary_value(primary_field)
    independent_value = getattr(independent, independent_field)
    status = _comparison_status(primary_value, independent_value, normalizer_kind)
    primary_present = primary_field is not None
    independent_present = _shown(independent_value) is not None
    winning_source: FieldSource | None = None

    if primary_present:
      winning_source = FieldSource.DOCUMENT_INTELLIGENCE
      field_sources[field] = winning_source
    elif independent_present:
      if not isinstance(independent_value, str | date | Decimal):
        raise TypeError("Independent fallback has an unsupported scalar type.")
      winning_source = FieldSource.LLM_FALLBACK
      field_sources[field] = winning_source
      updates[field] = _fallback_field(
        independent_value,
        merged_currency,
        normalizer_kind,
      )
      fallback_fields.append(field)

    if status == ComparisonStatus.DIFFERENT:
      conflict_fields.append(field)

    comparisons.append(
      FieldComparison(
        field=field,
        label=label,
        status=status,
        document_intelligence_value=_shown(primary_value),
        llm_value=_shown(independent_value),
        winning_source=winning_source,
      )
    )

  if isinstance(primary, InvoiceDocument):
    merged: NormalizedDocument = primary.model_copy(update=updates)
  elif isinstance(primary, ReceiptDocument):
    merged = primary.model_copy(update=updates)
  else:
    raise TypeError("Unsupported normalized document type.")

  evidence = DocumentReconciliation(
    comparisons=tuple(comparisons),
    fallback_fields=tuple(fallback_fields),
    conflict_fields=tuple(conflict_fields),
    field_sources=field_sources,
  )
  return merged, evidence
