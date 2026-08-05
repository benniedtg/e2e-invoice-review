from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from pathlib import Path

from app.invoices.validation import ValidationIssue, ValidationIssueCode
from app.schemas import DocumentType, InvoiceDocument, NormalizedDocument, ReceiptDocument

_DECIMAL_FIELDS = {"subtotal", "total_tax", "invoice_total"}
_DATE_FIELDS = {"invoice_date", "due_date"}
_IDENTIFIER_FIELDS = {
  "customer_vat_id",
  "invoice_number",
  "purchase_order",
  "vendor_vat_id",
}
EXPECTED_CORPUS_DOCUMENTS = 13
EXPECTED_CORPUS_PAGES = 14
ADVISORY_ISSUE_CODES = frozenset({ValidationIssueCode.LOW_CONFIDENCE})
_DUPLICATE_PREREQUISITES = {
  "10-de-duplicate.pdf": "03-de-happy-modern.pdf",
}


@dataclass(frozen=True, slots=True)
class ManifestEntry:
  filename: str
  document_type: DocumentType
  expected: Mapping[str, object]
  expected_issue_codes: tuple[str, ...]
  pages: int


def load_manifest(path: Path) -> tuple[ManifestEntry, ...]:
  """Load and enforce the complete fictional corpus contract."""
  try:
    raw_entries = json.loads(path.read_text(encoding="utf-8"))
  except JSONDecodeError as error:
    raise ValueError("Manifest must contain valid JSON.") from error
  if not isinstance(raw_entries, list):
    raise ValueError("Manifest must contain a list of document entries.")

  entries: list[ManifestEntry] = []
  for raw_entry in raw_entries:
    if not isinstance(raw_entry, Mapping):
      raise ValueError("Manifest entry must be an object.")
    filename = raw_entry.get("filename")
    expected = raw_entry.get("expected")
    issue_codes = raw_entry.get("expected_issue_codes", [])
    pages = raw_entry.get("pages")
    if (
      not isinstance(filename, str)
      or not isinstance(expected, Mapping)
      or not isinstance(issue_codes, list)
      or not all(isinstance(code, str) for code in issue_codes)
      or not isinstance(pages, int)
      or isinstance(pages, bool)
      or pages < 1
    ):
      raise ValueError("Manifest entry has an invalid required field.")
    try:
      document_type = DocumentType(raw_entry["document_type"])
    except (KeyError, ValueError) as error:
      raise ValueError("Manifest entry has an invalid document type.") from error
    entries.append(ManifestEntry(
      filename=filename,
      document_type=document_type,
      expected=dict(expected),
      expected_issue_codes=tuple(issue_codes),
      pages=pages,
    ))
  manifest = require_complete_corpus(tuple(entries))
  filenames = {entry.filename for entry in manifest}
  if len(filenames) != len(manifest):
    raise ValueError("Manifest filenames must be unique.")
  return manifest


def require_complete_corpus(
  entries: tuple[ManifestEntry, ...],
) -> tuple[ManifestEntry, ...]:
  """Reject empty or truncated inputs before a full provider run can begin."""
  if (
    len(entries) != EXPECTED_CORPUS_DOCUMENTS
    or sum(entry.pages for entry in entries) != EXPECTED_CORPUS_PAGES
  ):
    raise ValueError(
      "Manifest must contain exactly 13 documents totaling 14 pages."
    )
  return entries


def select_entries(
  entries: tuple[ManifestEntry, ...],
  filenames: tuple[str, ...] | list[str],
) -> tuple[ManifestEntry, ...]:
  """Select paid checks in manifest order without hiding duplicate prerequisites."""
  if not filenames:
    return entries

  requested = set(filenames)
  available = {entry.filename for entry in entries}
  missing = requested - available
  if missing:
    raise ValueError(f"Unknown manifest filename(s): {', '.join(sorted(missing))}")
  for duplicate, prerequisite in _DUPLICATE_PREREQUISITES.items():
    if duplicate in requested and prerequisite not in requested:
      raise ValueError(
        f"{duplicate} requires {prerequisite}; include both filenames so the "
        "duplicate context is evaluated without a hidden paid call."
      )
  return tuple(entry for entry in entries if entry.filename in requested)


def review_values(document: NormalizedDocument) -> dict[str, object]:
  """Project either normalized document into the manifest's common fields."""
  if isinstance(document, InvoiceDocument):
    return {
      "document_type": document.document_type,
      "vendor_name": _field_value(document.vendor_name),
      "vendor_vat_id": _field_value(document.vendor_vat_id),
      "customer_name": _field_value(document.customer_name),
      "customer_vat_id": _field_value(document.customer_vat_id),
      "invoice_number": _field_value(document.invoice_number),
      "invoice_date": _field_value(document.invoice_date),
      "due_date": _field_value(document.due_date),
      "purchase_order": _field_value(document.purchase_order),
      "currency": _field_value(document.currency),
      "subtotal": _money_value(document.subtotal),
      "total_tax": _money_value(document.total_tax),
      "invoice_total": _money_value(document.invoice_total),
    }
  if isinstance(document, ReceiptDocument):
    return {
      "document_type": document.document_type,
      "vendor_name": _field_value(document.merchant_name),
      "vendor_vat_id": None,
      "customer_name": None,
      "customer_vat_id": None,
      "invoice_number": None,
      "invoice_date": _field_value(document.transaction_date),
      "due_date": None,
      "purchase_order": None,
      "currency": _field_value(document.currency),
      "subtotal": _money_value(document.subtotal),
      "total_tax": _money_value(document.total_tax),
      "invoice_total": _money_value(document.total),
    }
  raise TypeError("Unsupported normalized document type.")


def compare_fields(
  expected: Mapping[str, object],
  actual: Mapping[str, object],
) -> dict[str, bool]:
  """Compare typed manifest values while tolerating harmless display variation."""
  return {
    name: _values_match(name, expected_value, actual.get(name))
    for name, expected_value in expected.items()
  }


def duplicate_code(
  document: NormalizedDocument,
  seen_invoice_keys: set[tuple[str, str]],
) -> ValidationIssueCode | None:
  """Record invoice keys in order and flag later supplier/invoice duplicates."""
  if not isinstance(document, InvoiceDocument):
    return None
  vendor_name = _field_value(document.vendor_name)
  invoice_number = _field_value(document.invoice_number)
  if not isinstance(vendor_name, str) or not isinstance(invoice_number, str):
    return None
  key = (_normal_text(vendor_name), _normal_identifier(invoice_number))
  if key in seen_invoice_keys:
    return ValidationIssueCode.DUPLICATE_INVOICE
  seen_invoice_keys.add(key)
  return None


def policy_issue_codes(issues: tuple[ValidationIssue, ...]) -> tuple[str, ...]:
  """Project the deterministic policy outcomes the manifest actually contracts.

  `low_confidence` reports how sure the primary provider was about a field it
  nonetheless read correctly. It is advisory, never blocks approval, and moves with
  provider model versions, so it is provider telemetry rather than a document defect
  the corpus can label. Every deterministic code — including advisory ones like
  `purchase_order_missing` — stays in the comparison.
  """
  return tuple(
    issue.code.value for issue in issues if issue.code not in ADVISORY_ISSUE_CODES
  )


def _field_value(field: object) -> object | None:
  return getattr(field, "value", None)


def _money_value(field: object) -> Decimal | None:
  money = _field_value(field)
  return getattr(money, "amount", None)


def _values_match(name: str, expected: object, actual: object) -> bool:
  if expected is None:
    return actual is None
  if actual is None:
    return False
  if name in _DECIMAL_FIELDS:
    try:
      return Decimal(str(expected)) == Decimal(str(actual))
    except InvalidOperation:
      return False
  if name in _DATE_FIELDS:
    try:
      expected_date = date.fromisoformat(str(expected))
    except ValueError:
      return False
    return expected_date == actual
  if name in _IDENTIFIER_FIELDS:
    return _normal_identifier(str(expected)) == _normal_identifier(str(actual))
  return _normal_text(str(expected)) == _normal_text(str(actual))


def _normal_text(value: str) -> str:
  return " ".join(value.casefold().split())


def _normal_identifier(value: str) -> str:
  return "".join(character for character in value.casefold() if character.isalnum())
