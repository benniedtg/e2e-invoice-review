from __future__ import annotations

from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.common import DocumentType, ExtractedField, Money, StrictSchema


class ReceiptPayment(StrictSchema):
  """One payment recorded on a receipt."""

  method: ExtractedField[str] | None = None
  amount: ExtractedField[Money] | None = None


class ReceiptTaxDetail(StrictSchema):
  """One receipt tax row with its numeric rate."""

  amount: ExtractedField[Money] | None = None
  rate: ExtractedField[Decimal] | None = None
  net_amount: ExtractedField[Money] | None = None
  description: ExtractedField[str] | None = None


class ReceiptItem(StrictSchema):
  """One normalized receipt line item."""

  description: ExtractedField[str] | None = None
  quantity: ExtractedField[Decimal] | None = None
  price: ExtractedField[Money] | None = None
  total_price: ExtractedField[Money] | None = None
  product_code: ExtractedField[str] | None = None
  quantity_unit: ExtractedField[str] | None = None


class ReceiptDocument(StrictSchema):
  """Provider-independent receipt extraction used by the review workflow."""

  document_type: Literal[DocumentType.RECEIPT] = DocumentType.RECEIPT
  document_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
  merchant_name: ExtractedField[str] | None = None
  merchant_address: ExtractedField[str] | None = None
  merchant_phone: ExtractedField[str] | None = None
  transaction_date: ExtractedField[Date] | None = None
  transaction_time: ExtractedField[Time] | None = None
  expense_category: ExtractedField[str] | None = None
  country_region: ExtractedField[str] | None = None
  currency: ExtractedField[str] | None = None
  subtotal: ExtractedField[Money] | None = None
  total_tax: ExtractedField[Money] | None = None
  total: ExtractedField[Money] | None = None
  tip: ExtractedField[Money] | None = None
  payments: tuple[ReceiptPayment, ...] = ()
  tax_details: tuple[ReceiptTaxDetail, ...] = ()
  items: tuple[ReceiptItem, ...] = ()
