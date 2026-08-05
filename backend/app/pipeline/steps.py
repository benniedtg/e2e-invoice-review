from __future__ import annotations

from typing import Protocol

from app.config import NorthstarPolicy
from app.document_review import (
  DocumentReviewer,
  ReviewDocumentType,
  merge_document_extractions,
)
from app.invoices.validation import ValidationContext, validate_document
from app.pipeline.classification import (
  ClassificationType,
  DocumentClassification,
  GeneralLedgerClassification,
)
from app.pipeline.core import (
  Pipeline,
  PipelineContext,
  PipelineStateError,
  StepDecision,
)
from app.schemas import DocumentType, NormalizedDocument


class DocumentExtractor(Protocol):
  """Provider-independent normalized extraction operation."""

  def extract(
    self,
    document_bytes: bytes,
    document_type: DocumentType,
  ) -> NormalizedDocument:
    """Extract one document with the selected financial-document model."""
    ...


class GeneralLedgerClassificationOperation(Protocol):
  """Provider-independent GL classification over normalized document data only."""

  def classify(self, document: NormalizedDocument) -> GeneralLedgerClassification:
    """Return a locally validated GL classification for one financial document."""
    ...


class IndependentDocumentReviewStep:
  """Read the original document independently and derive its classification."""

  step_id = "document_review"

  def __init__(self, reviewer: DocumentReviewer) -> None:
    self._reviewer = reviewer

  def run(self, context: PipelineContext) -> StepDecision:
    """Store one strict source reading and stop unsupported documents."""
    review = self._reviewer.review(
      context.document_bytes,
      context.mime_type,
    )
    context.independent_review = review
    context.classification = DocumentClassification(
      document_type=ClassificationType(review.document_type.value),
      reason=review.reason,
    )
    if review.document_type == ReviewDocumentType.OTHER:
      return StepDecision.STOP
    return StepDecision.CONTINUE


class RoutedPrimaryExtractionStep:
  """Route the original bytes to the matching primary DI extractor."""

  step_id = "primary_extraction"

  def __init__(self, extractor: DocumentExtractor) -> None:
    self._extractor = extractor

  def run(self, context: PipelineContext) -> StepDecision:
    """Store the primary normalized extraction selected by the source reading."""
    review = context.require_independent_review(type(self).__name__)
    if review.document_type == ReviewDocumentType.OTHER:
      return StepDecision.STOP

    document_type = DocumentType(review.document_type.value)
    document = self._extractor.extract(context.document_bytes, document_type)
    if document.document_type != document_type:
      raise PipelineStateError(
        f"{type(self).__name__} received a {document.document_type.value} "
        f"document from the {document_type.value} extractor."
      )
    context.primary_document = document
    return StepDecision.CONTINUE


class ReconciliationStep:
  """Merge primary and independent scalar evidence with DI remaining primary."""

  step_id = "reconciliation"

  def run(self, context: PipelineContext) -> StepDecision:
    """Store the effective document and visible comparison evidence."""
    document, reconciliation = merge_document_extractions(
      context.require_primary_document(type(self).__name__),
      context.require_independent_review(type(self).__name__),
    )
    context.document = document
    context.reconciliation = reconciliation
    return StepDecision.CONTINUE


class FinancialValidationStep:
  """Apply pure deterministic rules to a normalized financial document."""

  step_id = "validation"

  def __init__(self, policy: NorthstarPolicy) -> None:
    self._policy = policy

  def run(self, context: PipelineContext) -> StepDecision:
    """Store validation after requiring the merged normalized document."""
    document = context.require_document(type(self).__name__)
    context.require_general_ledger(type(self).__name__)
    context.validation = validate_document(
      document,
      ValidationContext(policy=self._policy),
    )
    return StepDecision.CONTINUE


class GeneralLedgerClassificationStep:
  """Classify the extracted document against Northstar's fixed GL catalog."""

  step_id = "general_ledger"

  def __init__(self, classifier: GeneralLedgerClassificationOperation) -> None:
    self._classifier = classifier

  def run(self, context: PipelineContext) -> StepDecision:
    """Store GL selection after requiring normalized extraction state."""
    context.general_ledger = self._classifier.classify(
      context.require_document(type(self).__name__)
    )
    return StepDecision.CONTINUE


def build_document_pipeline(
  reviewer: DocumentReviewer,
  extractor: DocumentExtractor,
  general_ledger_classifier: GeneralLedgerClassificationOperation,
  policy: NorthstarPolicy,
) -> Pipeline:
  """Build independent review, primary extraction, merge, GL, and validation."""
  return Pipeline(
    [
      IndependentDocumentReviewStep(reviewer),
      RoutedPrimaryExtractionStep(extractor),
      ReconciliationStep(),
      GeneralLedgerClassificationStep(general_ledger_classifier),
      FinancialValidationStep(policy),
    ]
  )
