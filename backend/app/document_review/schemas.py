from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import StrictSchema


class ReviewDocumentType(StrEnum):
  INVOICE = "invoice"
  RECEIPT = "receipt"
  OTHER = "other"


class IndependentDocumentReview(StrictSchema):
  """One strict reading of the original document, independent from DI output."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  document_type: ReviewDocumentType
  reason: str = Field(min_length=1, max_length=200)
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
  expense_category: Literal["fuel", "meals", "travel", "supplies", "other"] | None = None
  receipt_total: Decimal | None = None
  tip: Decimal | None = None

  @model_validator(mode="after")
  def validate_document_shape(self) -> IndependentDocumentReview:
    """Keep invoice, receipt, and non-financial readings mutually exclusive."""
    invoice_only_fields = (
      "vendor_name",
      "vendor_vat_id",
      "customer_name",
      "customer_vat_id",
      "invoice_number",
      "invoice_date",
      "due_date",
      "purchase_order",
      "total_discount",
      "invoice_total",
      "amount_due",
    )
    receipt_only_fields = (
      "merchant_name",
      "transaction_date",
      "expense_category",
      "receipt_total",
      "tip",
    )
    financial_fields = invoice_only_fields + receipt_only_fields + (
      "currency",
      "subtotal",
      "total_tax",
    )

    if self.document_type == ReviewDocumentType.OTHER:
      forbidden = financial_fields
    elif self.document_type == ReviewDocumentType.INVOICE:
      forbidden = receipt_only_fields
    else:
      forbidden = invoice_only_fields

    populated = [field for field in forbidden if getattr(self, field) is not None]
    if populated:
      fields = ", ".join(populated)
      raise ValueError(
        f"{self.document_type.value} review cannot carry fields for another document type: "
        f"{fields}."
      )
    return self


class FieldSource(StrEnum):
  DOCUMENT_INTELLIGENCE = "document_intelligence"
  LLM_FALLBACK = "llm_fallback"
  HUMAN = "human"


class ComparisonStatus(StrEnum):
  MATCH = "match"
  DIFFERENT = "different"
  MISSING_IN_LLM = "missing_in_llm"
  MISSING_IN_DOCUMENT_INTELLIGENCE = "missing_in_document_intelligence"
  MISSING_IN_BOTH = "missing_in_both"


class FieldComparison(StrictSchema):
  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  field: str
  label: str
  status: ComparisonStatus
  document_intelligence_value: str | None
  llm_value: str | None
  winning_source: FieldSource | None


class DocumentReconciliation(StrictSchema):
  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  comparisons: tuple[FieldComparison, ...]
  fallback_fields: tuple[str, ...]
  conflict_fields: tuple[str, ...]
  field_sources: dict[str, FieldSource]
