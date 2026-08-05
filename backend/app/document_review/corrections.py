from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from app.document_review.schemas import DocumentReconciliation, FieldSource
from app.schemas import ExtractedField, InvoiceDocument, Money, NormalizedDocument, ReceiptDocument
from app.schemas.common import StrictSchema


class InvalidCorrectionError(ValueError):
  """A correction names a field that does not belong to the stored document."""


class DocumentCorrections(StrictSchema):
  """The complete scalar correction surface for invoices and receipts."""

  vendor_name: str | None = None
  vendor_vat_id: str | None = None
  customer_name: str | None = None
  customer_vat_id: str | None = None
  invoice_number: str | None = None
  invoice_date: date | None = None
  due_date: date | None = None
  purchase_order: str | None = None
  currency: str | None = None
  subtotal: Decimal | None = None
  total_discount: Decimal | None = None
  total_tax: Decimal | None = None
  invoice_total: Decimal | None = None
  amount_due: Decimal | None = None
  merchant_name: str | None = None
  transaction_date: date | None = None
  expense_category: str | None = None
  receipt_total: Decimal | None = None
  tip: Decimal | None = None


_INVOICE_FIELDS = frozenset({
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
  "amount_due",
})
_RECEIPT_FIELDS = frozenset({
  "merchant_name",
  "transaction_date",
  "expense_category",
  "currency",
  "subtotal",
  "total_tax",
  "receipt_total",
  "tip",
})
_DATE_FIELDS = frozenset({"invoice_date", "due_date", "transaction_date"})
_MONEY_FIELDS = frozenset({
  "subtotal",
  "total_discount",
  "total_tax",
  "invoice_total",
  "amount_due",
  "receipt_total",
  "tip",
})
_FIELD_NAMES = {"receipt_total": "total"}


def apply_field_overrides(
  merged: NormalizedDocument,
  overrides: Mapping[str, object],
) -> NormalizedDocument:
  """Apply human scalar values without mutating immutable merged evidence."""
  normalized = DocumentCorrections.model_validate(dict(overrides)).model_dump(
    exclude_unset=True,
  )
  allowed = _allowed_fields(merged)
  invalid = normalized.keys() - allowed
  if invalid:
    fields = ", ".join(sorted(invalid))
    raise InvalidCorrectionError(
      f"Correction field(s) do not apply to this document type: {fields}."
    )

  currency = _effective_currency(merged, normalized)
  updates: dict[str, object] = {}
  for correction_name, value in normalized.items():
    document_name = document_field_name(correction_name)
    if value is None:
      updates[document_name] = None
    elif correction_name in _MONEY_FIELDS:
      updates[document_name] = ExtractedField[Money](
        value=Money(amount=value, currency_code=currency),
      )
    elif correction_name in _DATE_FIELDS:
      updates[document_name] = ExtractedField[date](value=value)
    else:
      updates[document_name] = ExtractedField[str](value=value)
  return merged.model_copy(update=updates)


def effective_field_sources(
  reconciliation: DocumentReconciliation,
  overrides: Mapping[str, object],
) -> dict[str, FieldSource]:
  """Overlay human provenance without changing source-comparison evidence."""
  sources = dict(reconciliation.field_sources)
  for correction_name in overrides:
    sources[document_field_name(correction_name)] = FieldSource.HUMAN
  return sources


def document_field_name(correction_name: str) -> str:
  """Map an API correction name to its normalized document attribute."""
  return _FIELD_NAMES.get(correction_name, correction_name)


def _allowed_fields(document: NormalizedDocument) -> frozenset[str]:
  if isinstance(document, InvoiceDocument):
    return _INVOICE_FIELDS
  if isinstance(document, ReceiptDocument):
    return _RECEIPT_FIELDS
  raise TypeError("Unsupported normalized document type.")


def _effective_currency(
  document: NormalizedDocument,
  overrides: Mapping[str, object],
) -> str | None:
  if "currency" in overrides:
    value = overrides["currency"]
    return value if isinstance(value, str) else None
  return document.currency.value if document.currency is not None else None
