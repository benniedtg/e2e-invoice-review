"""Pure checks on extracted receipt facts, reported before any policy is consulted."""

from __future__ import annotations

from datetime import date

from app.claims.schemas import (
  DateFact,
  FieldStatus,
  ReceiptFacts,
  ReceiptIssue,
  ReceiptIssueCode,
)

EARLIEST_PLAUSIBLE_DATE = date(2000, 1, 1)


def with_plausible_dates(facts: ReceiptFacts, today: date) -> ReceiptFacts:
  """Turn a misread date (before 2000 or in the future) into an unclear field to ask about."""

  def checked(fact: DateFact) -> DateFact:
    if fact.value is None or EARLIEST_PLAUSIBLE_DATE <= fact.value <= today:
      return fact
    return DateFact(
      status=FieldStatus.UNCLEAR,
      note=f"Read as {fact.value.isoformat()}, which cannot be right.",
    )

  return facts.model_copy(update={
    "receipt_date": checked(facts.receipt_date),
    "lines": tuple(
      line.model_copy(update={"service_date": checked(line.service_date)})
      for line in facts.lines
    ),
  })

_LINE_FIELDS = {
  "description": "description",
  "service_date": "service date",
  "item_code": "item code",
  "amount_charged": "amount charged",
  "amount_paid": "amount paid",
}


def receipt_issues(facts: ReceiptFacts, today: date) -> tuple[ReceiptIssue, ...]:
  """Flag unreadable fields and facts that cannot be right, without guessing fixes."""
  issues: list[ReceiptIssue] = []
  if not facts.lines:
    issues.append(ReceiptIssue(
      code=ReceiptIssueCode.NO_SERVICE_LINES,
      message="No service lines could be read from this receipt.",
    ))
  if facts.provider_number.status != FieldStatus.CLEAR:
    issues.append(ReceiptIssue(
      code=ReceiptIssueCode.PROVIDER_NUMBER_MISSING,
      field="provider_number",
      message=(
        "The provider number is missing or unreadable. Insurers usually need it, so ask "
        "the provider for an itemised receipt."
      ),
    ))
  for index, line in enumerate(facts.lines):
    for name, label in _LINE_FIELDS.items():
      fact = getattr(line, name)
      if fact.status == FieldStatus.UNCLEAR:
        note = f": {fact.note}" if fact.note else ""
        issues.append(ReceiptIssue(
          code=ReceiptIssueCode.UNCLEAR_FIELD,
          line_index=index,
          field=name,
          message=f"Line {index + 1}: the {label} is unclear{note}.",
        ))
    charged = line.amount_charged.value
    paid = line.amount_paid.value
    if charged is not None and paid is not None and paid > charged:
      issues.append(ReceiptIssue(
        code=ReceiptIssueCode.PAID_EXCEEDS_CHARGED,
        line_index=index,
        field="amount_paid",
        message=f"Line {index + 1}: the amount paid is more than the amount charged.",
      ))
    service_date = line.service_date.value
    if service_date is not None and service_date > today:
      issues.append(ReceiptIssue(
        code=ReceiptIssueCode.FUTURE_SERVICE_DATE,
        line_index=index,
        field="service_date",
        message=f"Line {index + 1}: the service date is in the future.",
      ))
  return tuple(issues)
