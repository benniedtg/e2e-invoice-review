from app.schemas.common import DocumentType, ExtractedField, Money
from app.schemas.invoice import InvoiceDocument
from app.schemas.receipt import ReceiptDocument

type NormalizedDocument = InvoiceDocument | ReceiptDocument

__all__ = [
  "DocumentType",
  "ExtractedField",
  "InvoiceDocument",
  "Money",
  "NormalizedDocument",
  "ReceiptDocument",
]
