from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import ConfigDict, Field, model_validator

from app.document_review import (
  DocumentReconciliation,
  IndependentDocumentReview,
  ReviewDocumentType,
)
from app.invoices.validation import ValidationReport
from app.pipeline.classification import (
  ClassificationType,
  DocumentClassification,
  GeneralLedgerClassification,
)
from app.schemas import DocumentType, InvoiceDocument, NormalizedDocument, ReceiptDocument
from app.schemas.common import StrictSchema


class PipelineStateError(RuntimeError):
  """A pipeline step ran without state that an earlier step must produce."""

  @classmethod
  def missing(cls, *, step_name: str, prerequisite: str) -> PipelineStateError:
    return cls(f"{step_name} requires {prerequisite} before it can run.")


class StepDecision(StrEnum):
  """Control whether a pipeline proceeds to its next configured step."""

  CONTINUE = "continue"
  STOP = "stop"


class PipelineStatus(StrEnum):
  """Terminal states exposed to downstream consumers."""

  COMPLETED = "completed"
  UNSUPPORTED = "unsupported"


class StepPhase(StrEnum):
  """Progress an observer can be told about one step."""

  STARTED = "started"
  COMPLETED = "completed"
  SKIPPED = "skipped"


class StepObserver(Protocol):
  """Reporting sink notified as steps run. It must never raise."""

  def __call__(self, step_id: str, phase: StepPhase) -> None:
    """Record that one identified step reached one phase."""
    ...


def _ignore_step(step_id: str, phase: StepPhase) -> None:
  """Discard progress when no caller asked to observe it."""


type RoutedDocument = Annotated[
  InvoiceDocument | ReceiptDocument,
  Field(discriminator="document_type"),
]


class PipelineResult(StrictSchema):
  """Strict terminal result for a classified financial document."""

  model_config = ConfigDict(extra="forbid", frozen=True)

  status: PipelineStatus
  classification: DocumentClassification
  independent_review: IndependentDocumentReview | None = None
  primary_document: RoutedDocument | None = None
  reconciliation: DocumentReconciliation | None = None
  document: RoutedDocument | None = None
  general_ledger: GeneralLedgerClassification | None = None
  validation: ValidationReport | None = None

  @model_validator(mode="after")
  def validate_terminal_state(self) -> PipelineResult:
    """Keep completed and unsupported result shapes mutually exclusive."""
    classification_type = self.classification.document_type

    if self.status == PipelineStatus.UNSUPPORTED:
      if classification_type != ClassificationType.OTHER:
        raise ValueError("Unsupported results require an 'other' classification.")
      if (
        self.independent_review is not None
        or self.primary_document is not None
        or self.reconciliation is not None
        or self.document is not None
        or self.general_ledger is not None
        or self.validation is not None
      ):
        raise ValueError(
          "Unsupported results cannot contain financial pipeline artifacts."
        )
      return self

    if classification_type == ClassificationType.OTHER:
      raise ValueError("Completed results require an invoice or receipt classification.")
    if self.independent_review is None:
      raise ValueError("Completed results require an independent document review.")
    if self.primary_document is None:
      raise ValueError("Completed results require a primary normalized document.")
    if self.reconciliation is None:
      raise ValueError("Completed results require reconciliation evidence.")
    if self.document is None:
      raise ValueError("Completed results require a merged normalized document.")
    if self.general_ledger is None:
      raise ValueError("Completed results require a GL classification.")
    if self.validation is None:
      raise ValueError("Completed results require a validation report.")

    expected_document_type = DocumentType(classification_type.value)
    expected_review_type = ReviewDocumentType(classification_type.value)
    if self.independent_review.document_type != expected_review_type:
      raise ValueError("Classification and independent review types must match.")
    if self.primary_document.document_type != expected_document_type:
      raise ValueError("Classification and primary document types must match.")
    if self.document.document_type != expected_document_type:
      raise ValueError("Classification and merged document types must match.")
    return self


@dataclass(slots=True)
class PipelineContext:
  """Mutable internal state passed through an ordered set of pipeline steps."""

  document_bytes: bytes
  mime_type: str
  classification: DocumentClassification | None = None
  independent_review: IndependentDocumentReview | None = None
  primary_document: NormalizedDocument | None = None
  reconciliation: DocumentReconciliation | None = None
  document: NormalizedDocument | None = None
  general_ledger: GeneralLedgerClassification | None = None
  validation: ValidationReport | None = None

  def require_classification(self, step_name: str) -> DocumentClassification:
    """Return classification state or name the missing prerequisite."""
    if self.classification is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="classification",
      )
    return self.classification

  def require_independent_review(
    self,
    step_name: str,
  ) -> IndependentDocumentReview:
    """Return independent source reading or name the missing prerequisite."""
    if self.independent_review is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="independent document review",
      )
    return self.independent_review

  def require_primary_document(self, step_name: str) -> NormalizedDocument:
    """Return primary DI extraction or name the missing prerequisite."""
    if self.primary_document is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="primary normalized document extraction",
      )
    return self.primary_document

  def require_reconciliation(self, step_name: str) -> DocumentReconciliation:
    """Return merge evidence or name the missing prerequisite."""
    if self.reconciliation is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="document reconciliation",
      )
    return self.reconciliation

  def require_document(self, step_name: str) -> NormalizedDocument:
    """Return merged normalized document or name the missing prerequisite."""
    if self.document is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="merged normalized document",
      )
    return self.document

  def require_validation(self, step_name: str) -> ValidationReport:
    """Return validation state or name the missing prerequisite."""
    if self.validation is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="financial validation",
      )
    return self.validation

  def require_general_ledger(self, step_name: str) -> GeneralLedgerClassification:
    """Return GL state or name the missing prerequisite."""
    if self.general_ledger is None:
      raise PipelineStateError.missing(
        step_name=step_name,
        prerequisite="general ledger classification",
      )
    return self.general_ledger

  def to_result(self) -> PipelineResult:
    """Convert internal state to the strict downstream boundary."""
    classification = self.require_classification("Pipeline completion")
    if classification.document_type == ClassificationType.OTHER:
      return PipelineResult(
        status=PipelineStatus.UNSUPPORTED,
        classification=classification,
      )

    return PipelineResult(
      status=PipelineStatus.COMPLETED,
      classification=classification,
      independent_review=self.require_independent_review("Pipeline completion"),
      primary_document=self.require_primary_document("Pipeline completion"),
      reconciliation=self.require_reconciliation("Pipeline completion"),
      document=self.require_document("Pipeline completion"),
      general_ledger=self.require_general_ledger("Pipeline completion"),
      validation=self.require_validation("Pipeline completion"),
    )


class PipelineStep(Protocol):
  """One ordered, synchronous document-processing operation."""

  step_id: str
  """Stable identifier reported to observers and exposed over HTTP."""

  def run(self, context: PipelineContext) -> StepDecision:
    """Update pipeline state and choose whether processing should continue."""
    ...


class Pipeline:
  """Run injected steps in order and expose only a validated terminal result."""

  def __init__(self, steps: list[PipelineStep] | tuple[PipelineStep, ...]) -> None:
    self._steps = tuple(steps)

  def run(
    self,
    document_bytes: bytes,
    mime_type: str,
    on_step: StepObserver | None = None,
  ) -> PipelineResult:
    """Process one document through the configured ordered steps."""
    context = PipelineContext(document_bytes=document_bytes, mime_type=mime_type)
    report = _ignore_step if on_step is None else on_step

    for index, step in enumerate(self._steps):
      report(step.step_id, StepPhase.STARTED)
      decision = step.run(context)
      if not isinstance(decision, StepDecision):
        raise PipelineStateError(
          f"{type(step).__name__} returned an invalid pipeline step decision."
        )
      report(step.step_id, StepPhase.COMPLETED)

      if decision == StepDecision.STOP:
        for remaining in self._steps[index + 1 :]:
          report(remaining.step_id, StepPhase.SKIPPED)
        break

    return context.to_result()
