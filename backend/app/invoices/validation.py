from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import ConfigDict, model_validator
from stdnum.eu import vat

from app.config import NorthstarPolicy
from app.schemas import InvoiceDocument, NormalizedDocument, ReceiptDocument
from app.schemas.common import ExtractedField, StrictSchema

TOTAL_TOLERANCE = Decimal("0.01")


class ValidationIssueCode(StrEnum):
  """Stable identifiers for deterministic validation failures."""

  VENDOR_NAME_REQUIRED = "vendor_name_required"
  VENDOR_VAT_ID_REQUIRED = "vendor_vat_id_required"
  VENDOR_VAT_ID_INVALID = "vendor_vat_id_invalid"
  CUSTOMER_NAME_REQUIRED = "customer_name_required"
  CUSTOMER_NAME_MISMATCH = "customer_name_mismatch"
  CUSTOMER_VAT_ID_REQUIRED = "customer_vat_id_required"
  CUSTOMER_VAT_ID_INVALID = "customer_vat_id_invalid"
  CUSTOMER_VAT_ID_MISMATCH = "customer_vat_id_mismatch"
  INVOICE_NUMBER_REQUIRED = "invoice_number_required"
  INVOICE_DATE_REQUIRED = "invoice_date_required"
  INVOICE_TOTAL_REQUIRED = "invoice_total_required"
  INVOICE_TOTAL_NON_POSITIVE = "invoice_total_non_positive"
  CURRENCY_REQUIRED = "currency_required"
  DUE_DATE_BEFORE_INVOICE_DATE = "due_date_before_invoice_date"
  INVOICE_TOTAL_MISMATCH = "invoice_total_mismatch"
  PURCHASE_ORDER_MISSING = "purchase_order_missing"
  MERCHANT_NAME_REQUIRED = "merchant_name_required"
  TRANSACTION_DATE_REQUIRED = "transaction_date_required"
  RECEIPT_CURRENCY_REQUIRED = "receipt_currency_required"
  RECEIPT_TOTAL_REQUIRED = "receipt_total_required"
  RECEIPT_TOTAL_NON_POSITIVE = "receipt_total_non_positive"
  RECEIPT_VAT_REQUIRED = "receipt_vat_required"
  RECEIPT_TOTAL_MISMATCH = "receipt_total_mismatch"
  LOW_CONFIDENCE = "low_confidence"
  DUPLICATE_INVOICE = "duplicate_invoice"
  DUPLICATE_FILE_CONTENT = "duplicate_file_content"


class ValidationSeverity(StrEnum):
  """Business impact assigned to a validation issue."""

  ERROR = "error"
  WARNING = "warning"


class ValidationIssue(StrictSchema):
  """One provider-independent business-rule failure."""

  model_config = ConfigDict(extra="forbid", frozen=True)

  code: ValidationIssueCode
  severity: ValidationSeverity
  field: str
  message: str
  expected: Decimal | None = None
  actual: Decimal | None = None


class ValidationReport(StrictSchema):
  """All deterministic issues and their derived validity decision."""

  model_config = ConfigDict(extra="forbid", frozen=True)

  issues: tuple[ValidationIssue, ...] = ()
  is_valid: bool = True

  @model_validator(mode="after")
  def derive_validity(self) -> ValidationReport:
    """Prevent callers or serialized data from overriding issue severity."""
    object.__setattr__(
      self,
      "is_valid",
      not any(issue.severity == ValidationSeverity.ERROR for issue in self.issues),
    )
    return self


@dataclass(frozen=True, slots=True)
class ValidationContext:
  """Facts supplied by orchestration without making policy stateful."""

  policy: NorthstarPolicy
  duplicate_code: ValidationIssueCode | None = None
  human_fields: frozenset[str] = frozenset()


def validate_invoice(
  document: InvoiceDocument,
  context: ValidationContext,
) -> ValidationReport:
  """Apply the fixed Northstar invoice rules to one normalized invoice."""
  issues: list[ValidationIssue] = []

  _require_text(issues, document.vendor_name, ValidationIssueCode.VENDOR_NAME_REQUIRED,
                "vendor_name", "Supplier name is required.")
  _validate_vat(
    issues,
    document.vendor_vat_id,
    ValidationIssueCode.VENDOR_VAT_ID_REQUIRED,
    ValidationIssueCode.VENDOR_VAT_ID_INVALID,
    "vendor_vat_id",
    "Supplier VAT ID is required.",
    "Supplier VAT ID does not have a valid EU format or checksum.",
  )
  _require_text(issues, document.customer_name, ValidationIssueCode.CUSTOMER_NAME_REQUIRED,
                "customer_name", "Customer name is required.")
  if _field_text(document.customer_name) is not None and not _same_text(
    _field_text(document.customer_name), context.policy.customer_name
  ):
    issues.append(_issue(
      ValidationIssueCode.CUSTOMER_NAME_MISMATCH,
      "customer_name",
      "Customer name does not match the configured Northstar customer.",
    ))
  _validate_vat(
    issues,
    document.customer_vat_id,
    ValidationIssueCode.CUSTOMER_VAT_ID_REQUIRED,
    ValidationIssueCode.CUSTOMER_VAT_ID_INVALID,
    "customer_vat_id",
    "Customer VAT ID is required.",
    "Customer VAT ID does not have a valid EU format or checksum.",
  )
  if _field_text(document.customer_vat_id) is not None and _compact_identifier(
    _field_text(document.customer_vat_id)
  ) != _compact_identifier(context.policy.customer_vat_id):
    issues.append(_issue(
      ValidationIssueCode.CUSTOMER_VAT_ID_MISMATCH,
      "customer_vat_id",
      "Customer VAT ID does not match the configured Northstar VAT ID.",
    ))
  _require_text(issues, document.invoice_number, ValidationIssueCode.INVOICE_NUMBER_REQUIRED,
                "invoice_number", "Invoice number is required.")
  if document.invoice_date is None:
    issues.append(_issue(
      ValidationIssueCode.INVOICE_DATE_REQUIRED,
      "invoice_date",
      "Invoice date is required.",
    ))
  if document.invoice_total is None:
    issues.append(_issue(
      ValidationIssueCode.INVOICE_TOTAL_REQUIRED,
      "invoice_total",
      "Invoice total is required.",
    ))
  elif document.invoice_total.value.amount <= 0:
    issues.append(_issue(
      ValidationIssueCode.INVOICE_TOTAL_NON_POSITIVE,
      "invoice_total",
      "Invoice total must be positive.",
    ))
  _require_text(issues, document.currency, ValidationIssueCode.CURRENCY_REQUIRED,
                "currency", "Invoice currency is required.")
  if (
    document.due_date is not None
    and document.invoice_date is not None
    and document.due_date.value < document.invoice_date.value
  ):
    issues.append(_issue(
      ValidationIssueCode.DUE_DATE_BEFORE_INVOICE_DATE,
      "due_date",
      "Due date cannot be before the invoice date.",
    ))

  if (
    document.subtotal is not None
    and document.total_tax is not None
    and document.invoice_total is not None
  ):
    discount = (
      document.total_discount.value.amount
      if document.total_discount is not None
      else Decimal("0")
    )
    expected = document.subtotal.value.amount - discount + document.total_tax.value.amount
    actual = document.invoice_total.value.amount
    if abs(expected - actual) > TOTAL_TOLERANCE:
      issues.append(
        ValidationIssue(
          code=ValidationIssueCode.INVOICE_TOTAL_MISMATCH,
          severity=ValidationSeverity.ERROR,
          field="invoice_total",
          message="Invoice total does not reconcile with subtotal, discount, and VAT.",
          expected=expected,
          actual=actual,
        )
      )

  if _field_text(document.purchase_order) is None:
    issues.append(ValidationIssue(
      code=ValidationIssueCode.PURCHASE_ORDER_MISSING,
      severity=ValidationSeverity.WARNING,
      field="purchase_order",
      message="Purchase order is missing; confirm whether one is required.",
    ))
  _append_low_confidence_issues(issues, document, context, _INVOICE_CORE_FIELDS)
  _append_duplicate_issue(issues, context.duplicate_code)
  return ValidationReport(issues=tuple(issues))


def validate_receipt(
  document: ReceiptDocument,
  context: ValidationContext,
) -> ValidationReport:
  """Apply the fixed Northstar receipt rules to one normalized receipt."""
  issues: list[ValidationIssue] = []

  _require_text(issues, document.merchant_name, ValidationIssueCode.MERCHANT_NAME_REQUIRED,
                "merchant_name", "Merchant name is required.")
  if document.transaction_date is None:
    issues.append(_issue(
      ValidationIssueCode.TRANSACTION_DATE_REQUIRED,
      "transaction_date",
      "Transaction date is required.",
    ))
  _require_text(issues, document.currency, ValidationIssueCode.RECEIPT_CURRENCY_REQUIRED,
                "currency", "Receipt currency is required.")
  if document.total is None:
    issues.append(_issue(
      ValidationIssueCode.RECEIPT_TOTAL_REQUIRED,
      "total",
      "Receipt total is required.",
    ))
  elif document.total.value.amount <= 0:
    issues.append(_issue(
      ValidationIssueCode.RECEIPT_TOTAL_NON_POSITIVE,
      "total",
      "Receipt total must be positive.",
    ))
  if document.total_tax is None:
    issues.append(_issue(
      ValidationIssueCode.RECEIPT_VAT_REQUIRED,
      "total_tax",
      "Receipt VAT total is required.",
    ))

  if (
    document.subtotal is not None
    and document.total_tax is not None
    and document.total is not None
  ):
    tip = document.tip.value.amount if document.tip is not None else Decimal("0")
    expected = document.subtotal.value.amount + document.total_tax.value.amount + tip
    actual = document.total.value.amount
    if abs(expected - actual) > TOTAL_TOLERANCE:
      issues.append(
        ValidationIssue(
          code=ValidationIssueCode.RECEIPT_TOTAL_MISMATCH,
          severity=ValidationSeverity.ERROR,
          field="total",
          message="Receipt total does not reconcile with subtotal, VAT, and tip.",
          expected=expected,
          actual=actual,
        )
      )

  _append_low_confidence_issues(issues, document, context, _RECEIPT_CORE_FIELDS)
  _append_duplicate_issue(issues, context.duplicate_code)
  return ValidationReport(issues=tuple(issues))


def validate_document(
  document: NormalizedDocument,
  context: ValidationContext,
) -> ValidationReport:
  """Apply the deterministic policy for a normalized document type."""
  if isinstance(document, InvoiceDocument):
    return validate_invoice(document, context)
  return validate_receipt(document, context)


def build_duplicate_issue(code: ValidationIssueCode) -> ValidationIssue:
  """Describe a duplicate that a caller has already found in storage."""
  if code == ValidationIssueCode.DUPLICATE_FILE_CONTENT:
    return ValidationIssue(
      code=code,
      severity=ValidationSeverity.ERROR,
      field="document",
      message="This exact file has already been uploaded.",
    )
  return ValidationIssue(
    code=ValidationIssueCode.DUPLICATE_INVOICE,
    severity=ValidationSeverity.ERROR,
    field="invoice_number",
    message="An invoice with this supplier and invoice number already exists.",
  )


def with_issues(
  report: ValidationReport,
  issues: tuple[ValidationIssue, ...],
) -> ValidationReport:
  """Return a new report whose validity is re-derived from every issue."""
  if not issues:
    return report
  return ValidationReport(issues=report.issues + issues)


_INVOICE_CORE_FIELDS = (
  "vendor_name",
  "vendor_vat_id",
  "customer_name",
  "customer_vat_id",
  "invoice_number",
  "invoice_date",
  "currency",
  "subtotal",
  "total_tax",
  "invoice_total",
)
_RECEIPT_CORE_FIELDS = (
  "merchant_name",
  "transaction_date",
  "currency",
  "subtotal",
  "total_tax",
  "total",
)


def _issue(
  code: ValidationIssueCode,
  field: str,
  message: str,
) -> ValidationIssue:
  return ValidationIssue(
    code=code,
    severity=ValidationSeverity.ERROR,
    field=field,
    message=message,
  )


def _require_text(
  issues: list[ValidationIssue],
  field: ExtractedField[str] | None,
  code: ValidationIssueCode,
  name: str,
  message: str,
) -> None:
  if _field_text(field) is None:
    issues.append(_issue(code, name, message))


def _validate_vat(
  issues: list[ValidationIssue],
  field: ExtractedField[str] | None,
  required_code: ValidationIssueCode,
  invalid_code: ValidationIssueCode,
  name: str,
  required_message: str,
  invalid_message: str,
) -> None:
  value = _field_text(field)
  if value is None:
    issues.append(_issue(required_code, name, required_message))
  elif not vat.is_valid(value):
    issues.append(_issue(invalid_code, name, invalid_message))


def _append_duplicate_issue(
  issues: list[ValidationIssue],
  code: ValidationIssueCode | None,
) -> None:
  if code is not None:
    issues.append(build_duplicate_issue(code))


def _append_low_confidence_issues(
  issues: list[ValidationIssue],
  document: NormalizedDocument,
  context: ValidationContext,
  field_names: tuple[str, ...],
) -> None:
  for name in field_names:
    field = getattr(document, name)
    if (
      name not in context.human_fields
      and field is not None
      and field.confidence is not None
      and field.confidence < context.policy.minimum_primary_confidence
    ):
      issues.append(ValidationIssue(
        code=ValidationIssueCode.LOW_CONFIDENCE,
        severity=ValidationSeverity.WARNING,
        field=name,
        message="Primary extraction confidence is below the Northstar threshold.",
      ))


def _field_text(field: ExtractedField[str] | None) -> str | None:
  if field is None or not field.value.strip():
    return None
  return field.value


def _same_text(left: str | None, right: str) -> bool:
  return left is not None and " ".join(left.casefold().split()) == " ".join(
    right.casefold().split()
  )


def _compact_identifier(value: str) -> str:
  return "".join(character for character in value.casefold() if character.isalnum())
