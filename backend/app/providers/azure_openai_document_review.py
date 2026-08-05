from __future__ import annotations

from app.document_review import DocumentReviewer, IndependentDocumentReview
from app.providers.azure_openai import AzureOpenAIProvider

DOCUMENT_REVIEW_INSTRUCTIONS = (
  "Independently classify and extract the original financial document.\n"
  "Use invoice for a request for payment, receipt for an already-paid expense, "
  "and other when neither is clear.\n"
  "Extract only the strict top-level fields in the output schema.\n"
  "Use null when absent or unreadable.\n"
  "Do not validate VAT, decide policy or approval, choose a GL account, or invent "
  "values.\n"
  "Return dates and decimals through the schema types.\n"
)


class AzureOpenAIDocumentReviewer(DocumentReviewer):
  """Independently recognize and extract one original financial document."""

  def __init__(self, provider: AzureOpenAIProvider) -> None:
    self._provider = provider

  def review(
    self,
    document_bytes: bytes,
    mime_type: str,
  ) -> IndependentDocumentReview:
    """Return one strict reading of the original PDF or image."""
    return self._provider.analyze_document(
      document_bytes=document_bytes,
      mime_type=mime_type,
      instructions=DOCUMENT_REVIEW_INSTRUCTIONS,
      output_type=IndependentDocumentReview,
    )
