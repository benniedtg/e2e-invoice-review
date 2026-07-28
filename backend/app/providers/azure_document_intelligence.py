from __future__ import annotations

from collections.abc import Mapping
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError

from app.config import DocumentIntelligenceSettings
from app.schemas import DocumentType, ExtractedField, NormalizedDocument
from app.schemas.common import Money
from app.schemas.invoice import (
  InvoiceDocument,
  InvoiceItem,
  InvoiceTaxDetail,
  PaymentDetail,
)
from app.schemas.receipt import (
  ReceiptDocument,
  ReceiptItem,
  ReceiptPayment,
  ReceiptTaxDetail,
)

MODEL_IDS = {
  DocumentType.INVOICE: "prebuilt-invoice",
  DocumentType.RECEIPT: "prebuilt-receipt",
}


class DocumentIntelligenceError(Exception):
  """A safe provider or provider-mapping failure."""


class DocumentMappingError(DocumentIntelligenceError):
  """The provider result could not be normalized."""


def analyze_document(
  path: Path,
  document_type: DocumentType,
  settings: DocumentIntelligenceSettings,
) -> dict[str, Any]:
  """Analyze one document and return its serializable Azure result."""
  credential = AzureKeyCredential(settings.key.get_secret_value())
  try:
    with DocumentIntelligenceClient(
      endpoint=str(settings.endpoint),
      credential=credential,
    ) as client:
      with path.open("rb") as document:
        poller = client.begin_analyze_document(MODEL_IDS[document_type], body=document)
        return poller.result().as_dict()
  except AzureError:
    raise DocumentIntelligenceError(
      "Azure Document Intelligence request failed."
    ) from None


def map_document(
  raw_result: Mapping[str, Any],
  document_type: DocumentType,
) -> NormalizedDocument:
  """Map a raw Azure result into the selected normalized document schema."""
  documents = raw_result.get("documents")
  if not isinstance(documents, list) or not documents:
    raise DocumentMappingError("Azure returned no analyzed document to map.")

  document = documents[0]
  if not isinstance(document, Mapping):
    raise DocumentMappingError("Azure returned an unusable analyzed document.")

  fields = document.get("fields")
  if not isinstance(fields, Mapping):
    raise DocumentMappingError("Azure returned no document fields to map.")

  document_confidence = _confidence(document.get("confidence"), "document")
  if document_type is DocumentType.INVOICE:
    return _map_invoice(fields, document_confidence)
  return _map_receipt(fields, document_confidence)


def _map_invoice(
  fields: Mapping[str, Any],
  document_confidence: float | None,
) -> InvoiceDocument:
  subtotal = _money_field(fields, "SubTotal")
  total_discount = _money_field(fields, "TotalDiscount")
  total_tax = _money_field(fields, "TotalTax")
  invoice_total = _money_field(fields, "InvoiceTotal")
  amount_due = _money_field(fields, "AmountDue")
  return InvoiceDocument(
    document_confidence=document_confidence,
    vendor_name=_string_field(fields, "VendorName"),
    vendor_address=_content_field(fields, "VendorAddress"),
    vendor_vat_id=_string_field(fields, "VendorTaxId"),
    customer_name=_string_field(fields, "CustomerName"),
    customer_address=_content_field(fields, "CustomerAddress"),
    customer_vat_id=_string_field(fields, "CustomerTaxId"),
    invoice_number=_string_field(fields, "InvoiceId"),
    invoice_date=_date_field(fields, "InvoiceDate"),
    due_date=_date_field(fields, "DueDate"),
    purchase_order=_string_field(fields, "PurchaseOrder"),
    payment_term=_string_field(fields, "PaymentTerm"),
    currency=_currency_field(invoice_total, subtotal, total_tax, amount_due, total_discount),
    subtotal=subtotal,
    total_discount=total_discount,
    total_tax=total_tax,
    invoice_total=invoice_total,
    amount_due=amount_due,
    payment_details=[
      PaymentDetail(
        iban=_string_field(item, "IBAN"),
        swift=_string_field(item, "SWIFT"),
        bank_account_number=_string_field(item, "BankAccountNumber"),
      )
      for item in _object_values(fields, "PaymentDetails")
    ],
    tax_details=[
      InvoiceTaxDetail(
        amount=_money_field(item, "Amount"),
        rate=_string_field(item, "Rate"),
      )
      for item in _object_values(fields, "TaxDetails")
    ],
    items=[_map_invoice_item(item) for item in _object_values(fields, "Items")],
  )


def _map_invoice_item(fields: Mapping[str, Any]) -> InvoiceItem:
  return InvoiceItem(
    description=_string_field(fields, "Description"),
    quantity=_number_field(fields, "Quantity"),
    unit_price=_money_field(fields, "UnitPrice"),
    amount=_money_field(fields, "Amount"),
    product_code=_string_field(fields, "ProductCode"),
    tax=_money_field(fields, "Tax"),
    tax_rate=_string_field(fields, "TaxRate"),
    unit=_string_field(fields, "Unit"),
    date=_date_field(fields, "Date"),
  )


def _map_receipt(
  fields: Mapping[str, Any],
  document_confidence: float | None,
) -> ReceiptDocument:
  subtotal = _money_field(fields, "Subtotal")
  total_tax = _money_field(fields, "TotalTax")
  total = _money_field(fields, "Total")
  tip = _money_field(fields, "Tip")
  return ReceiptDocument(
    document_confidence=document_confidence,
    merchant_name=_string_field(fields, "MerchantName"),
    merchant_address=_content_field(fields, "MerchantAddress"),
    merchant_phone=_special_string_field(fields, "MerchantPhoneNumber", "valuePhoneNumber"),
    transaction_date=_date_field(fields, "TransactionDate"),
    transaction_time=_time_field(fields, "TransactionTime"),
    expense_category=_string_field(fields, "ReceiptType"),
    country_region=_special_string_field(fields, "CountryRegion", "valueCountryRegion"),
    currency=_currency_field(total, subtotal, total_tax, tip),
    subtotal=subtotal,
    total_tax=total_tax,
    total=total,
    tip=tip,
    payments=[
      ReceiptPayment(
        method=_string_field(item, "Method"),
        amount=_money_field(item, "Amount"),
      )
      for item in _object_values(fields, "Payments")
    ],
    tax_details=[
      ReceiptTaxDetail(
        amount=_money_field(item, "Amount"),
        rate=_number_field(item, "Rate"),
        net_amount=_money_field(item, "NetAmount"),
        description=_string_field(item, "Description"),
      )
      for item in _object_values(fields, "TaxDetails")
    ],
    items=[_map_receipt_item(item) for item in _object_values(fields, "Items")],
  )


def _map_receipt_item(fields: Mapping[str, Any]) -> ReceiptItem:
  return ReceiptItem(
    description=_string_field(fields, "Description"),
    quantity=_number_field(fields, "Quantity"),
    price=_money_field(fields, "Price"),
    total_price=_money_field(fields, "TotalPrice"),
    product_code=_string_field(fields, "ProductCode"),
    quantity_unit=_string_field(fields, "QuantityUnit"),
  )


def _field(fields: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
  value = fields.get(name)
  if value is None:
    return None
  if not isinstance(value, Mapping):
    raise DocumentMappingError(f"Azure field {name} has an unusable shape.")
  return value


def _object_values(fields: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
  field = _field(fields, name)
  if field is None:
    return []
  values = field.get("valueArray")
  if values is None:
    return []
  if not isinstance(values, list):
    raise DocumentMappingError(f"Azure field {name} is not a usable list.")

  objects: list[Mapping[str, Any]] = []
  for value in values:
    if not isinstance(value, Mapping):
      raise DocumentMappingError(f"Azure field {name} contains an unusable item.")
    item = value.get("valueObject")
    if not isinstance(item, Mapping):
      raise DocumentMappingError(f"Azure field {name} contains no usable object.")
    objects.append(item)
  return objects


def _string_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[str] | None:
  return _special_string_field(fields, name, "valueString")


def _special_string_field(
  fields: Mapping[str, Any],
  name: str,
  value_key: str,
) -> ExtractedField[str] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = field.get(value_key)
  if not isinstance(value, str) or not value.strip():
    value = _content(field)
  if value is None:
    return None
  return _wrap(field, value, name)


def _content_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[str] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = _content(field)
  if value is None:
    return None
  return _wrap(field, value, name)


def _date_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[Date] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = field.get("valueDate")
  if isinstance(value, DateTime):
    normalized = value.date()
  elif isinstance(value, Date):
    normalized = value
  elif isinstance(value, str):
    try:
      normalized = Date.fromisoformat(value)
    except ValueError:
      raise DocumentMappingError(f"Azure field {name} has an unusable date.") from None
  elif value is None:
    return None
  else:
    raise DocumentMappingError(f"Azure field {name} has an unusable date.")
  return _wrap(field, normalized, name)


def _time_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[Time] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = field.get("valueTime")
  if isinstance(value, Time):
    normalized = value
  elif isinstance(value, str):
    try:
      normalized = Time.fromisoformat(value)
    except ValueError:
      raise DocumentMappingError(f"Azure field {name} has an unusable time.") from None
  elif value is None:
    return None
  else:
    raise DocumentMappingError(f"Azure field {name} has an unusable time.")
  return _wrap(field, normalized, name)


def _number_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[Decimal] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = field.get("valueNumber")
  is_percentage = False
  if value is None:
    content = _content(field)
    is_percentage = bool(content and content.rstrip().endswith("%"))
    value = content.rstrip().rstrip("%").strip() if content else None
  if value is None:
    return None
  normalized = _decimal(value, name)
  if is_percentage:
    normalized /= Decimal("100")
  return _wrap(field, normalized, name)


def _money_field(
  fields: Mapping[str, Any],
  name: str,
) -> ExtractedField[Money] | None:
  field = _field(fields, name)
  if field is None:
    return None
  value = field.get("valueCurrency")
  if value is None:
    return None
  if not isinstance(value, Mapping) or value.get("amount") is None:
    raise DocumentMappingError(f"Azure field {name} has an unusable currency value.")
  money = Money(
    amount=_decimal(value["amount"], name),
    currency_code=_optional_string(value.get("currencyCode")),
    currency_symbol=_optional_string(value.get("currencySymbol")),
  )
  return _wrap(field, money, name)


def _currency_field(
  *money_fields: ExtractedField[Money] | None,
) -> ExtractedField[str] | None:
  for field in money_fields:
    if field is None:
      continue
    value = field.value.currency_code or field.value.currency_symbol
    if value:
      return ExtractedField(
        value=value,
        content=field.content,
        confidence=field.confidence,
      )
  return None


def _wrap[T](
  field: Mapping[str, Any],
  value: T,
  name: str,
) -> ExtractedField[T]:
  return ExtractedField(
    value=value,
    content=_content(field),
    confidence=_confidence(field.get("confidence"), name),
  )


def _content(field: Mapping[str, Any]) -> str | None:
  return _optional_string(field.get("content"))


def _optional_string(value: Any) -> str | None:
  if not isinstance(value, str):
    return None
  stripped = value.strip()
  return stripped or None


def _decimal(value: Any, name: str) -> Decimal:
  if isinstance(value, bool):
    raise DocumentMappingError(f"Azure field {name} has an unusable number.")
  try:
    return Decimal(str(value))
  except (InvalidOperation, ValueError):
    raise DocumentMappingError(f"Azure field {name} has an unusable number.") from None


def _confidence(value: Any, name: str) -> float | None:
  if value is None:
    return None
  if isinstance(value, bool):
    raise DocumentMappingError(f"Azure field {name} has unusable confidence.")
  try:
    confidence = float(value)
  except (TypeError, ValueError):
    raise DocumentMappingError(f"Azure field {name} has unusable confidence.") from None
  if not 0.0 <= confidence <= 1.0:
    raise DocumentMappingError(f"Azure field {name} has unusable confidence.")
  return confidence
