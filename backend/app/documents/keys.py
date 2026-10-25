from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.schemas import (
  ExtractedField,
  InvoiceDocument,
  Money,
  NormalizedDocument,
  ReceiptDocument,
)

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class DocumentIdentity:
  """Display values and duplicate-matching keys for one stored document."""

  vendor_name: str | None = None
  invoice_number: str | None = None
  vendor_name_key: str | None = None
  invoice_number_key: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentFacts:
  """Effective values copied into columns so stored reviews can be queried.

  Field names are the column names they are stored under.
  """

  document_date: date | None = None
  total_cents: int | None = None
  currency: str | None = None
  vendor_search_key: str | None = None


def to_cents(amount: Decimal) -> int:
  """Store money on a fixed two-decimal scale so SQL sums stay exact."""
  return int(amount.quantize(CENT, rounding=ROUND_HALF_UP).scaleb(2))


def from_cents(cents: int) -> Decimal:
  """Turn a stored two-decimal integer back into an amount."""
  return Decimal(cents).scaleb(-2)


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


def document_facts(document: NormalizedDocument | None) -> DocumentFacts:
  """Project the effective date, total, currency, and supplier for querying."""
  if isinstance(document, InvoiceDocument):
    return _facts(
      document.vendor_name,
      document.invoice_date,
      document.invoice_total,
      document.currency,
    )
  if isinstance(document, ReceiptDocument):
    return _facts(
      document.merchant_name,
      document.transaction_date,
      document.total,
      document.currency,
    )
  return DocumentFacts()


def _facts(
  vendor: ExtractedField[str] | None,
  document_date: ExtractedField[date] | None,
  total: ExtractedField[Money] | None,
  currency: ExtractedField[str] | None,
) -> DocumentFacts:
  """Build one projection from the fields both document types share."""
  vendor_name = _field_value(vendor)
  currency_code = (_field_value(currency) or "").strip().upper()
  return DocumentFacts(
    document_date=document_date.value if document_date is not None else None,
    total_cents=to_cents(total.value.amount) if total is not None else None,
    currency=currency_code or None,
    vendor_search_key=normalize_name(vendor_name) if vendor_name is not None else None,
  )


def _field_value(field: object) -> str | None:
  """Read one extracted string value without assuming it was found."""
  value = getattr(field, "value", None)
  return value if isinstance(value, str) else None
