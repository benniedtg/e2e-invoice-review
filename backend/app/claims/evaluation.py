"""Pure eligibility rules: compare verified policy conditions with receipt facts and answers.

The model reads the policy; this module decides. Each condition becomes satisfied, not
satisfied, unknown (naming the fact that would settle it), or plain information.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.claims.estimate import money
from app.claims.schemas import (
  AssessedLine,
  ClaimAnswers,
  Condition,
  ConditionKind,
  ConditionResult,
  ConditionState,
  Outcome,
  ReceiptFacts,
  Slot,
)

NEED_ORDER = (
  Slot.SERVICE_DESCRIPTION,
  Slot.COVER_START_DATE,
  Slot.HAS_REFERRAL,
  Slot.BENEFITS_USED,
  Slot.AMOUNT_PAID,
)
"""The order in which the chat asks for facts the outcome depends on."""


@dataclass(frozen=True, slots=True)
class EffectiveLine:
  """One receipt line after the student's answers replace unclear or vague fields."""

  line_index: int
  description: str | None
  item_code: str | None
  service_date: date | None
  amount_charged: Decimal | None
  amount_paid: Decimal | None


@dataclass(frozen=True, slots=True)
class LineEvaluation:
  """The decided outcome for one line and the facts still needed."""

  outcome: Outcome
  reasons: tuple[str, ...]
  needs: tuple[Slot, ...]
  results: tuple[ConditionResult, ...]


def effective_lines(facts: ReceiptFacts, answers: ClaimAnswers) -> list[EffectiveLine]:
  """Merge printed facts with answers; a fully paid total marks every line as paid."""
  charges = [line.amount_charged.value for line in facts.lines]
  paid_in_full = (
    facts.total_paid.value is not None
    and all(charge is not None for charge in charges)
    and facts.total_paid.value == sum(charge for charge in charges if charge is not None)
  )
  lines: list[EffectiveLine] = []
  for index, line in enumerate(facts.lines):
    paid = answers.amounts_paid.get(index, line.amount_paid.value)
    if paid is None and paid_in_full:
      paid = line.amount_charged.value
    lines.append(EffectiveLine(
      line_index=index,
      description=answers.service_descriptions.get(index, line.description.value),
      item_code=line.item_code.value,
      service_date=answers.service_dates.get(index, line.service_date.value),
      amount_charged=line.amount_charged.value,
      amount_paid=paid,
    ))
  return lines


def evaluate_line(
  line: EffectiveLine,
  assessed: AssessedLine,
  answers: ClaimAnswers,
  today: date,
) -> LineEvaluation:
  """Decide one line's outcome from its verified conditions."""
  results = tuple(
    _evaluate(condition, line, answers, today) for condition in assessed.conditions
  )

  if not assessed.description_specific_enough and line.line_index not in (
    answers.service_descriptions
  ):
    return LineEvaluation(
      outcome=Outcome.MORE_INFORMATION_NEEDED,
      reasons=("The receipt does not say specifically what this service was.",),
      needs=(Slot.SERVICE_DESCRIPTION,),
      results=results,
    )

  exclusions = [
    result
    for result in results
    if result.condition.kind == ConditionKind.EXCLUSION
    and result.state == ConditionState.NOT_SATISFIED
  ]
  covers = [
    result
    for result in results
    if result.condition.kind == ConditionKind.COVERAGE
    and result.state == ConditionState.SATISFIED
  ]
  refuses = [
    result
    for result in results
    if result.condition.kind == ConditionKind.COVERAGE
    and result.state == ConditionState.NOT_SATISFIED
  ]
  if exclusions:
    return _decided(Outcome.APPEARS_EXCLUDED, exclusions, results)
  if refuses and not covers:
    return _decided(Outcome.APPEARS_EXCLUDED, refuses, results)
  if refuses and covers:
    return LineEvaluation(
      outcome=Outcome.MORE_INFORMATION_NEEDED,
      reasons=(
        "The policy text found points both ways for this service; check it with "
        "your insurer.",
      ),
      needs=(),
      results=results,
    )

  failures = [
    result
    for result in results
    if result.state == ConditionState.NOT_SATISFIED
  ]
  if failures:
    return _decided(Outcome.APPEARS_NOT_ELIGIBLE, failures, results)

  # An exclusion with an exception only the insurer can settle is never resolved by guessing.
  conditional = [
    result
    for result in results
    if result.condition.kind == ConditionKind.EXCLUSION
    and result.state == ConditionState.UNKNOWN
  ]
  if conditional:
    return LineEvaluation(
      outcome=Outcome.MORE_INFORMATION_NEEDED,
      reasons=tuple(result.explanation for result in conditional),
      needs=(),
      results=results,
    )

  needs = {result_need for result in results if (result_need := _need(result)) is not None}
  if not covers:
    return LineEvaluation(
      outcome=Outcome.MORE_INFORMATION_NEEDED,
      reasons=(
        "No clause in this product's policy was found that covers this service.",
      ),
      needs=_ordered(needs),
      results=results,
    )
  if line.amount_paid is None and any(
    result.condition.kind == ConditionKind.BENEFIT_RATE for result in results
  ):
    needs.add(Slot.AMOUNT_PAID)
  if needs:
    return LineEvaluation(
      outcome=Outcome.MORE_INFORMATION_NEEDED,
      reasons=tuple(
        result.explanation for result in results if result.state == ConditionState.UNKNOWN
      ),
      needs=_ordered(needs),
      results=results,
    )
  return _decided(Outcome.APPEARS_ELIGIBLE, covers, results)


def add_months(start: date, months: int) -> date:
  """Move a date forward by whole months, clamping to the last day of short months."""
  month_index = start.month - 1 + months
  year = start.year + month_index // 12
  month = month_index % 12 + 1
  day = min(start.day, calendar.monthrange(year, month)[1])
  return date(year, month, day)


def _evaluate(
  condition: Condition,
  line: EffectiveLine,
  answers: ClaimAnswers,
  today: date,
) -> ConditionResult:
  place = where(condition)
  kind = condition.kind

  if kind == ConditionKind.COVERAGE:
    if condition.applies:
      return _result(condition, ConditionState.SATISFIED, f"{place} covers this service.")
    return _result(
      condition,
      ConditionState.NOT_SATISFIED,
      f"{place} says this product does not pay for this service.",
    )

  if kind == ConditionKind.EXCLUSION:
    if condition.applies and condition.exception:
      return _result(
        condition,
        ConditionState.UNKNOWN,
        f"{place} excludes it unless {condition.exception.rstrip('.')}. Ask your insurer "
        "whether this service meets that exception.",
      )
    if condition.applies:
      return _result(condition, ConditionState.NOT_SATISFIED, f"{place} excludes it.")
    return _result(condition, ConditionState.INFORMATION, f"{place} excludes other services.")

  if kind == ConditionKind.PRE_EXISTING_WAITING_PERIOD and condition.months is not None:
    return _result(
      condition,
      ConditionState.INFORMATION,
      f"{place} sets a {condition.months}-month waiting period only for conditions that "
      "existed before your cover started; your insurer decides whether that applies.",
    )

  if kind == ConditionKind.WAITING_PERIOD and condition.months is not None:
    if answers.cover_start_date is None or line.service_date is None:
      return _result(
        condition,
        ConditionState.UNKNOWN,
        f"{place} sets a {condition.months}-month waiting period; it depends on when "
        "your cover started.",
      )
    ends = add_months(answers.cover_start_date, condition.months)
    if line.service_date >= ends:
      return _result(
        condition,
        ConditionState.SATISFIED,
        f"The {condition.months}-month waiting period in {place} ended on {ends}.",
      )
    return _result(
      condition,
      ConditionState.NOT_SATISFIED,
      f"The {condition.months}-month waiting period in {place} only ends on {ends}, "
      f"after this service on {line.service_date}.",
    )

  if kind == ConditionKind.REFERRAL_REQUIRED and condition.applies:
    if answers.has_referral is None:
      return _result(
        condition,
        ConditionState.UNKNOWN,
        f"{place} requires a referral for this service.",
      )
    if answers.has_referral:
      return _result(condition, ConditionState.SATISFIED, "You had the referral it needs.")
    return _result(
      condition,
      ConditionState.NOT_SATISFIED,
      f"{place} requires a referral, and you did not have one.",
    )

  if kind == ConditionKind.ANNUAL_LIMIT and condition.amount is not None:
    used = answers.benefits_used.get(line.line_index)
    if used is None:
      return _result(
        condition,
        ConditionState.UNKNOWN,
        f"{place} sets an annual limit of {money(condition.amount)}; it depends on what "
        "has already been paid this year.",
      )
    if used >= condition.amount:
      return _result(
        condition,
        ConditionState.NOT_SATISFIED,
        f"The {money(condition.amount)} annual limit in {place} is already used.",
      )
    return _result(
      condition,
      ConditionState.SATISFIED,
      f"{money(condition.amount - used)} of the {money(condition.amount)} annual limit in "
      f"{place} remains.",
    )

  if kind == ConditionKind.CLAIM_TIME_LIMIT and condition.months is not None:
    if line.service_date is None:
      return _result(condition, ConditionState.INFORMATION, f"{place} sets a claim time limit.")
    deadline = add_months(line.service_date, condition.months)
    if today > deadline:
      return _result(
        condition,
        ConditionState.NOT_SATISFIED,
        f"{place} required the claim by {deadline}.",
      )
    return _result(
      condition,
      ConditionState.SATISFIED,
      f"{place} allows claiming until {deadline}.",
    )

  return _result(condition, ConditionState.INFORMATION, f"{place} sets a condition.")


def _need(result: ConditionResult) -> Slot | None:
  if result.state != ConditionState.UNKNOWN:
    return None
  return {
    ConditionKind.WAITING_PERIOD: Slot.COVER_START_DATE,
    ConditionKind.REFERRAL_REQUIRED: Slot.HAS_REFERRAL,
    ConditionKind.ANNUAL_LIMIT: Slot.BENEFITS_USED,
  }.get(result.condition.kind)


def _ordered(needs: set[Slot]) -> tuple[Slot, ...]:
  return tuple(slot for slot in NEED_ORDER if slot in needs)


def _decided(
  outcome: Outcome,
  deciding: Sequence[ConditionResult],
  results: tuple[ConditionResult, ...],
) -> LineEvaluation:
  return LineEvaluation(
    outcome=outcome,
    reasons=tuple(result.explanation for result in deciding),
    needs=(),
    results=results,
  )


def _result(condition: Condition, state: ConditionState, explanation: str) -> ConditionResult:
  return ConditionResult(condition=condition, state=state, explanation=explanation)


def where(condition: Condition) -> str:
  """Name a cited passage: its section number when it has one, else its heading and page."""
  citation = condition.citation
  if citation.section_number and citation.section_number.startswith("Schedule"):
    return f"{citation.section_number} (page {citation.page})"
  if citation.section_number:
    return f"Section {citation.section_number} (page {citation.page})"
  if citation.section_title:
    return f"“{citation.section_title}” (page {citation.page})"
  return f"page {citation.page} of the policy"
