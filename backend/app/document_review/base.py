from typing import Protocol

from app.document_review.schemas import IndependentDocumentReview


class DocumentReviewError(Exception):
  """The independent source-document reading failed safely."""


class DocumentReviewer(Protocol):
  def review(
    self,
    document_bytes: bytes,
    mime_type: str,
  ) -> IndependentDocumentReview:
    """Classify and independently extract one original document."""
    pass
