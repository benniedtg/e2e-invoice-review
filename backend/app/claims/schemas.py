"""Contracts for the OSHC claim checker: receipt facts, evidence, answers, and outcomes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import StrictSchema


class FieldStatus(StrEnum):
  """How confidently one receipt field could be read."""

  CLEAR = "clear"
  UNCLEAR = "unclear"
  ABSENT = "absent"


def _require_status_value(status: FieldStatus, value: object) -> None:
  """Keep unreadable fields empty so nothing downstream sees a guess."""
  if status == FieldStatus.CLEAR and value is None:
    raise ValueError("A clear field needs its value.")
  if status != FieldStatus.CLEAR and value is not None:
    raise ValueError("An unclear or absent field must not carry a value.")


class TextFact(StrictSchema):
  """One printed text field and how clearly it could be read."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  value: str | None = Field(default=None, min_length=1, max_length=200)
  status: FieldStatus
  note: str | None = Field(default=None, max_length=160)

  @model_validator(mode="after")
  def check_status(self) -> TextFact:
    """Reject a value on a field that was not read clearly."""
    _require_status_value(self.status, self.value)
    return self


class DateFact(StrictSchema):
  """One printed date and how clearly it could be read."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  value: date | None = None
  status: FieldStatus
  note: str | None = Field(default=None, max_length=160)

  @model_validator(mode="after")
  def check_status(self) -> DateFact:
    """Reject a value on a field that was not read clearly."""
    _require_status_value(self.status, self.value)
    return self


class MoneyFact(StrictSchema):
  """One printed Australian-dollar amount and how clearly it could be read."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  value: Decimal | None = Field(default=None, ge=0)
  status: FieldStatus
  note: str | None = Field(default=None, max_length=160)

  @model_validator(mode="after")
  def check_status(self) -> MoneyFact:
    """Reject a value on a field that was not read clearly."""
    _require_status_value(self.status, self.value)
    return self


class ServiceLineFacts(StrictSchema):
  """One service printed on a receipt."""

  description: TextFact
  service_date: DateFact
  item_code: TextFact
  amount_charged: MoneyFact
  amount_paid: MoneyFact


class ReceiptFacts(StrictSchema):
  """Facts printed on one health receipt. The patient's name is never extracted."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  is_health_receipt: bool
  reason: str = Field(min_length=1, max_length=200)
  provider_name: TextFact
  provider_type: TextFact
  provider_number: TextFact
  receipt_date: DateFact
  total_charged: MoneyFact
  total_paid: MoneyFact
  lines: tuple[ServiceLineFacts, ...] = Field(default=(), max_length=20)


class ReceiptIssueCode(StrEnum):
  """Deterministic problems found in extracted receipt facts."""

  NO_SERVICE_LINES = "no_service_lines"
  PAID_EXCEEDS_CHARGED = "paid_exceeds_charged"
  FUTURE_SERVICE_DATE = "future_service_date"
  UNCLEAR_FIELD = "unclear_field"
  PROVIDER_NUMBER_MISSING = "provider_number_missing"


class ReceiptIssue(StrictSchema):
  """One flagged receipt problem the student should know about."""

  code: ReceiptIssueCode
  line_index: int | None = None
  field: str | None = None
  message: str


class Slot(StrEnum):
  """Facts the checker may need to ask the student for."""

  INSURER = "insurer"
  PRODUCT = "product"
  SERVICE_DATE = "service_date"
  SERVICE_DESCRIPTION = "service_description"
  COVER_START_DATE = "cover_start_date"
  HAS_REFERRAL = "has_referral"
  BENEFITS_USED = "benefits_used"
  AMOUNT_PAID = "amount_paid"


type Amount = Annotated[Decimal, Field(ge=0, le=100_000)]
type Description = Annotated[str, Field(min_length=1, max_length=200)]


class ClaimAnswers(StrictSchema):
  """Everything the student has told the chat so far, held by the browser."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  insurer_id: str | None = Field(default=None, max_length=40)
  product_id: str | None = Field(default=None, max_length=60)
  cover_start_date: date | None = None
  has_referral: bool | None = None
  service_dates: dict[int, date] = Field(default_factory=dict)
  service_descriptions: dict[int, Description] = Field(default_factory=dict)
  amounts_paid: dict[int, Amount] = Field(default_factory=dict)
  benefits_used: dict[int, Amount] = Field(default_factory=dict)


class AnswerInput(StrEnum):
  """How the chat collects an answer."""

  CHOICE = "choice"
  DATE = "date"
  AMOUNT = "amount"
  YES_NO = "yes_no"
  TEXT = "text"


class QuestionOption(StrictSchema):
  """One quick reply."""

  value: str
  label: str


class NextQuestion(StrictSchema):
  """The single fact the checker needs next, and how to collect it."""

  slot: Slot
  line_index: int | None = None
  prompt: str
  input: AnswerInput
  options: tuple[QuestionOption, ...] = ()


class EvidenceAspect(StrEnum):
  """What a retrieved policy passage is evidence about."""

  COVERAGE = "coverage"
  EXCLUSIONS = "exclusions"
  DEFINITIONS = "definitions"
  WAITING_PERIODS = "waiting_periods"
  LIMITS = "limits"
  CLAIMS = "claims"


class ServiceCategory(StrEnum):
  """What kind of service one receipt line was."""

  GP_CONSULTATION = "gp_consultation"
  SPECIALIST_CONSULTATION = "specialist_consultation"
  OPTOMETRY_CONSULTATION = "optometry_consultation"
  GLASSES_OR_CONTACT_LENSES = "glasses_or_contact_lenses"
  DENTAL = "dental"
  PHYSIOTHERAPY = "physiotherapy"
  CHIROPRACTIC_OR_OSTEOPATHY = "chiropractic_or_osteopathy"
  PSYCHOLOGY = "psychology"
  PHARMACY = "pharmacy"
  PATHOLOGY_OR_IMAGING = "pathology_or_imaging"
  AMBULANCE = "ambulance"
  HOSPITAL = "hospital"
  OTHER = "other"


class ConditionKind(StrEnum):
  """One kind of rule a policy passage can establish for a service."""

  COVERAGE = "coverage"
  EXCLUSION = "exclusion"
  WAITING_PERIOD = "waiting_period"
  PRE_EXISTING_WAITING_PERIOD = "pre_existing_waiting_period"
  BENEFIT_RATE = "benefit_rate"
  PER_SERVICE_LIMIT = "per_service_limit"
  ANNUAL_LIMIT = "annual_limit"
  REFERRAL_REQUIRED = "referral_required"
  PROVIDER_REQUIREMENT = "provider_requirement"
  CLAIM_TIME_LIMIT = "claim_time_limit"
  CLAIM_DOCUMENT = "claim_document"


class LimitPeriod(StrEnum):
  """The period an annual limit resets over."""

  CALENDAR_YEAR = "calendar_year"
  FINANCIAL_YEAR = "financial_year"
  MEMBERSHIP_YEAR = "membership_year"
  POLICY_LIFETIME = "policy_lifetime"
  UNSPECIFIED = "unspecified"


class RateBasis(StrEnum):
  """What a benefit percentage is a percentage of."""

  AMOUNT_CHARGED = "amount_charged"
  MBS_FEE = "mbs_fee"
  OTHER = "other"


class ConditionDraft(StrictSchema):
  """One condition the model reads from a passage, before local verification."""

  kind: ConditionKind
  applies: bool
  months: int | None = None
  percent: Decimal | None = None
  amount: Decimal | None = None
  period: LimitPeriod | None = None
  basis: RateBasis | None = None
  detail: str | None = Field(default=None, max_length=200)
  exception: str | None = Field(default=None, max_length=200)
  chunk_id: int
  quote: str = Field(min_length=1, max_length=400)


class LineConditionsDraft(StrictSchema):
  """The model's reading of the evidence for one receipt line."""

  line_index: int
  category: ServiceCategory
  description_specific_enough: bool
  conditions: tuple[ConditionDraft, ...] = Field(default=(), max_length=16)


class ConditionsDraft(StrictSchema):
  """The model's reading of the evidence for every assessed line."""

  lines: tuple[LineConditionsDraft, ...]


class Citation(StrictSchema):
  """Where in which policy edition a verified quote appears."""

  document_id: str
  document_title: str
  section_number: str | None
  section_title: str | None
  page: int
  quote: str


class Condition(StrictSchema):
  """One condition whose quote was found word for word in the retrieved passage."""

  kind: ConditionKind
  applies: bool
  months: int | None = None
  percent: Decimal | None = None
  amount: Decimal | None = None
  period: LimitPeriod | None = None
  basis: RateBasis | None = None
  detail: str | None = None
  exception: str | None = None
  chunk_id: int
  citation: Citation


class AssessedLine(StrictSchema):
  """Verified conditions for one line, sent back by the browser to re-evaluate."""

  line_index: int
  document_id: str
  service_date: date
  description: str
  category: ServiceCategory
  description_specific_enough: bool
  conditions: tuple[Condition, ...]
  missing_aspects: tuple[EvidenceAspect, ...]


class AssessmentState(StrictSchema):
  """The verified reading of one receipt, so new answers need no model call."""

  product_id: str
  lines: tuple[AssessedLine, ...]


class Outcome(StrEnum):
  """The supported answer for one receipt line."""

  APPEARS_ELIGIBLE = "appears_eligible"
  APPEARS_EXCLUDED = "appears_excluded"
  APPEARS_NOT_ELIGIBLE = "appears_not_eligible"
  MORE_INFORMATION_NEEDED = "more_information_needed"


OUTCOME_LABELS = {
  Outcome.APPEARS_ELIGIBLE: "appears eligible",
  Outcome.APPEARS_EXCLUDED: "appears excluded",
  Outcome.APPEARS_NOT_ELIGIBLE: "appears not eligible",
  Outcome.MORE_INFORMATION_NEEDED: "more information needed",
}


class ConditionState(StrEnum):
  """How one condition compares with the receipt and the student's answers."""

  SATISFIED = "satisfied"
  NOT_SATISFIED = "not_satisfied"
  UNKNOWN = "unknown"
  INFORMATION = "information"


class ConditionResult(StrictSchema):
  """One condition and what it means for this line."""

  condition: Condition
  state: ConditionState
  explanation: str


class BenefitEstimate(StrictSchema):
  """A benefit computed only from verified rates and limits, with its working."""

  amount: Decimal | None
  steps: tuple[str, ...]
  note: str | None = None


class LineResult(StrictSchema):
  """The outcome for one receipt line, with the evidence that decided it."""

  line_index: int
  description: str | None
  amount_paid: Decimal | None
  outcome: Outcome
  reasons: tuple[str, ...]
  needs: tuple[Slot, ...]
  conditions: tuple[ConditionResult, ...]
  estimate: BenefitEstimate | None


class ClaimStep(StrictSchema):
  """One thing to do when lodging the claim, with its policy source."""

  text: str
  citation: Citation | None


class PolicyEdition(StrictSchema):
  """One policy edition used for this answer."""

  document_id: str
  title: str
  effective_basis: str


class PolicyContext(StrictSchema):
  """Which insurer, product, and editions an answer was drawn from."""

  insurer: str
  product: str
  editions: tuple[PolicyEdition, ...]


class ClaimResponse(StrictSchema):
  """One chat turn: either the next question or a supported result."""

  stage: Literal["question", "result"]
  message: str
  next_question: NextQuestion | None
  lines: tuple[LineResult, ...] = ()
  claim_steps: tuple[ClaimStep, ...] = ()
  policy: PolicyContext | None = None
  state: AssessmentState | None = None


class OutcomeMessage(StrictSchema):
  """The model's plain-English explanation of an already decided outcome."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  message: str = Field(min_length=1, max_length=1200)


class InterpretedAnswer(StrictSchema):
  """A typed reply mapped onto one question's format, or null when unclear."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  value: str | None = Field(default=None, max_length=200)
