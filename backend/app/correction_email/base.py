from typing import Protocol

from app.correction_email.schemas import CorrectionEmailDraft
from app.invoices import ValidationIssue
from app.schemas import NormalizedDocument


class CorrectionEmailDraftingError(RuntimeError):
  """A correction-email draft could not be generated safely."""


class CorrectionEmailDrafter(Protocol):
  """Provider-independent operation for one on-demand correction draft."""

  def draft(
    self,
    document: NormalizedDocument,
    issues: tuple[ValidationIssue, ...],
  ) -> CorrectionEmailDraft:
    """Draft one correction request from effective values and filtered issues."""
    ...
