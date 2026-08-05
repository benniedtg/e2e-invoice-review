from __future__ import annotations

from dataclasses import dataclass

from app.schemas import InvoiceDocument, NormalizedDocument, ReceiptDocument


@dataclass(frozen=True, slots=True)
class DocumentIdentity:
  """Display values and duplicate-matching keys for one stored document."""

  vendor_name: str | None = None
  invoice_number: str | None = None
  vendor_name_key: str | None = None
  invoice_number_key: str | None = None


def normalize_name(value: str) -> str:
  """Fold case and collapse whitespace so spacing cannot hide a match."""
  return " ".join(value.casefold().split())


def normalize_identifier(value: str) -> str:
  """Keep only alphanumerics so punctuation cannot hide a match."""
  return "".join(character for character in value.casefold() if character.isalnum())


def document_identity(document: NormalizedDocument | None) -> DocumentIdentity:
  """Derive display values and, for invoices only, duplicate-matching keys."""
  if isinstance(document, InvoiceDocument):
    return _invoice_identity(document)
  if isinstance(document, ReceiptDocument):
    return DocumentIdentity(vendor_name=_field_value(document.merchant_name))
  return DocumentIdentity()


def _invoice_identity(document: InvoiceDocument) -> DocumentIdentity:
  """Build invoice keys only when both halves of the key are present."""
  vendor_name = _field_value(document.vendor_name)
  invoice_number = _field_value(document.invoice_number)
  if vendor_name is None or invoice_number is None:
    return DocumentIdentity(vendor_name=vendor_name, invoice_number=invoice_number)

  return DocumentIdentity(
    vendor_name=vendor_name,
    invoice_number=invoice_number,
    vendor_name_key=normalize_name(vendor_name),
    invoice_number_key=normalize_identifier(invoice_number),
  )


def _field_value(field: object) -> str | None:
  """Read one extracted string value without assuming it was found."""
  value = getattr(field, "value", None)
  return value if isinstance(value, str) else None
