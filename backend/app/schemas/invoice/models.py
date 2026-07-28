from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.common import DocumentType, ExtractedField, Money, StrictSchema


class PaymentDetail(StrictSchema):
  """EU-relevant payment information found on an invoice."""

  iban: ExtractedField[str] | None = None
  swift: ExtractedField[str] | None = None
  bank_account_number: ExtractedField[str] | None = None


class InvoiceTaxDetail(StrictSchema):
  """One invoice tax amount and its reported text rate."""

  amount: ExtractedField[Money] | None = None
  rate: ExtractedField[str] | None = None


class InvoiceItem(StrictSchema):
  """One normalized invoice line item."""

  description: ExtractedField[str] | None = None
  quantity: ExtractedField[Decimal] | None = None
  unit_price: ExtractedField[Money] | None = None
  amount: ExtractedField[Money] | None = None
  product_code: ExtractedField[str] | None = None
  tax: ExtractedField[Money] | None = None
  tax_rate: ExtractedField[str] | None = None
  unit: ExtractedField[str] | None = None
  date: ExtractedField[Date] | None = None


class InvoiceDocument(StrictSchema):
  """Provider-independent invoice extraction used by the review workflow."""

  document_type: Literal[DocumentType.INVOICE] = DocumentType.INVOICE
  document_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
  vendor_name: ExtractedField[str] | None = None
  vendor_address: ExtractedField[str] | None = None
  vendor_vat_id: ExtractedField[str] | None = None
  customer_name: ExtractedField[str] | None = None
  customer_address: ExtractedField[str] | None = None
  customer_vat_id: ExtractedField[str] | None = None
  invoice_number: ExtractedField[str] | None = None
  invoice_date: ExtractedField[Date] | None = None
  due_date: ExtractedField[Date] | None = None
  purchase_order: ExtractedField[str] | None = None
  payment_term: ExtractedField[str] | None = None
  currency: ExtractedField[str] | None = None
  subtotal: ExtractedField[Money] | None = None
  total_discount: ExtractedField[Money] | None = None
  total_tax: ExtractedField[Money] | None = None
  invoice_total: ExtractedField[Money] | None = None
  amount_due: ExtractedField[Money] | None = None
  payment_details: list[PaymentDetail] = Field(default_factory=list)
  tax_details: list[InvoiceTaxDetail] = Field(default_factory=list)
  items: list[InvoiceItem] = Field(default_factory=list)
