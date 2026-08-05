"""Provider-independent correction-email eligibility and draft contracts."""

from app.correction_email.base import (
  CorrectionEmailDrafter,
  CorrectionEmailDraftingError,
)
from app.correction_email.eligibility import (
  SUPPLIER_FIXABLE_CODES,
  supplier_fixable_issues,
)
from app.correction_email.schemas import CorrectionEmailDraft

__all__ = [
  "SUPPLIER_FIXABLE_CODES",
  "CorrectionEmailDraft",
  "CorrectionEmailDrafter",
  "CorrectionEmailDraftingError",
  "supplier_fixable_issues",
]
