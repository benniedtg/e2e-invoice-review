from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

if __package__ in {None, ""}:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.claims import service  # noqa: E402
from app.claims.catalog import PRODUCTS_BY_ID, PolicyProduct, document_for  # noqa: E402
from app.claims.evaluation import effective_lines  # noqa: E402
from app.claims.retrieval import ServiceQuery, retrieve_evidence  # noqa: E402
from app.claims.schemas import (  # noqa: E402
  ClaimAnswers,
  Condition,
  NextQuestion,
  ReceiptFacts,
  Slot,
)
from app.documents.database import SessionFactory, initialize_database  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLAIMS_DIRECTORY = ROOT / "samples" / "claims"
MANIFEST_PATH = CLAIMS_DIRECTORY / "manifest.json"
RECEIPT_DIRECTORY = CLAIMS_DIRECTORY / "receipts"
MIME_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}
MAX_TURNS = 6
RETRIEVAL_SLOTS = frozenset({Slot.SERVICE_DATE, Slot.SERVICE_DESCRIPTION})
"""Answers that change what is searched, so they need a fresh assessment, as the UI does."""


class Tally:
  """Pass counts per metric, printing each failure where it happens."""

  def __init__(self) -> None:
    self.counts: dict[str, list[int]] = {}

  def check(self, metric: str, passed: bool, detail: str) -> None:
    count = self.counts.setdefault(metric, [0, 0])
    count[0] += passed
    count[1] += 1
    if not passed:
      print(f"      FAIL {metric}: {detail}")

  def all_passed(self) -> bool:
    return all(passed == total for passed, total in self.counts.values())


def main() -> int:
  parser = argparse.ArgumentParser(
    description=(
      "Evaluate the student-claims pipeline against samples/claims/manifest.json. Billable: "
      "each receipt is read once, and each check retrieves, reads conditions, and writes "
      "one message per turn."
    ),
  )
  parser.add_argument("receipts", nargs="*", help="Only evaluate these receipt filenames.")
  arguments = parser.parse_args()
  manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
  initialize_database()
  tally = Tally()
  errors = 0

  with SessionFactory() as session:
    for entry in manifest["receipts"]:
      if arguments.receipts and entry["receipt"] not in arguments.receipts:
        continue
      print(entry["receipt"])
      try:
        facts = _read(entry, tally)
        for check in entry.get("checks", []) if facts is not None else []:
          _run_check(session, facts, check, manifest["default_answers"], tally)
      except Exception as error:  # noqa: BLE001 - report every paid-operation failure
        errors += 1
        print(f"      ERROR {type(error).__name__}: {error}")

  print("\nSummary")
  for metric, (passed, total) in tally.counts.items():
    print(f"  {metric:<26} {passed}/{total}")
  print(f"  {'pipeline errors':<26} {errors}")
  return 0 if errors == 0 and tally.all_passed() else 1


def _read(entry: dict, tally: Tally) -> ReceiptFacts | None:
  """Stage 1: compare each labelled field's status and value."""
  path = RECEIPT_DIRECTORY / entry["receipt"]
  expected = entry["facts"]
  try:
    facts, _issues = service.extract_receipt(path.read_bytes(), MIME_TYPES[path.suffix])
  except service.NotHealthReceiptError:
    tally.check("health receipt", not expected["is_health_receipt"], "read as not a health receipt")
    return None
  tally.check("health receipt", expected["is_health_receipt"], "read as a health receipt")

  if "total_paid" in expected:
    _fact(tally, "total paid", facts.total_paid.status.value, facts.total_paid.value,
          expected["total_paid"])
  labelled_lines = expected.get("lines", [])
  if labelled_lines:
    tally.check("line count", len(facts.lines) == len(labelled_lines),
                f"expected {len(labelled_lines)}, read {len(facts.lines)}")
  for index, fields in enumerate(labelled_lines[:len(facts.lines)]):
    for name, label in fields.items():
      fact = getattr(facts.lines[index], name)
      _fact(tally, f"line {index} {name}", fact.status.value, fact.value, label)
  return facts


def _fact(tally: Tally, name: str, status: str, value: object, label: list) -> None:
  expected_status, expected_value = label
  tally.check("field status", status == expected_status,
              f"{name}: expected {expected_status}, got {status}")
  if expected_value is not None:
    if isinstance(value, Decimal):
      same = value == Decimal(expected_value)
    else:
      same = str(value) == expected_value
    tally.check("field value", same, f"{name}: expected {expected_value}, got {value}")


def _run_check(
  session: Session,
  facts: ReceiptFacts,
  check: dict,
  default_answers: dict[str, str | dict[str, str]],
  tally: Tally,
) -> None:
  """Stages 2-6: play the scripted conversation, then compare what it settled on."""
  product = PRODUCTS_BY_ID[check["product_id"]]
  script = {**default_answers, **check.get("answers", {})}
  answers = ClaimAnswers(insurer_id=product.insurer_id, product_id=product.id)
  print(f"  {product.id}")

  response = service.assess_claim(session, facts, answers)
  asked: list[str] = []
  while response.stage == "question" and response.next_question is not None:
    question = response.next_question
    asked.append(question.slot.value)
    if question.slot.value not in script or len(asked) > MAX_TURNS:
      print(f"      stopped at an unscripted question: {question.prompt}")
      break
    scripted = script[question.slot.value]
    if isinstance(scripted, dict):
      scripted = scripted.get(str(question.line_index))
      if scripted is None:
        print(f"      stopped at an unscripted line: {question.prompt}")
        break
    answers = _answered(answers, question, scripted)
    response = (
      service.assess_claim(session, facts, answers)
      if question.slot in RETRIEVAL_SLOTS or response.state is None
      else service.reassess_claim(session, facts, answers, response.state)
    )

  if "questions" in check:
    tally.check("question sequence", asked == check["questions"],
                f"expected {check['questions']}, asked {asked}")
  if "editions" in check:
    editions = sorted(edition.document_id for edition in response.policy.editions) \
      if response.policy is not None else []
    tally.check("policy edition", editions == sorted(check["editions"]),
                f"expected {check['editions']}, used {editions}")

  results = {line.line_index: line for line in response.lines}
  for key, label in check.get("lines", {}).items():
    result = results.get(int(key))
    if result is None:
      tally.check("outcome", False, f"line {key} has no result")
      continue
    tally.check("outcome", result.outcome.value == label["outcome"],
                f"line {key}: expected {label['outcome']}, got {result.outcome.value} "
                f"({' '.join(result.reasons)})")
    if "estimate" in label:
      amount = result.estimate.amount if result.estimate is not None else None
      wanted = None if label["estimate"] is None else Decimal(label["estimate"])
      tally.check("calculation", amount == wanted, f"line {key}: expected {wanted}, got {amount}")

  for key, wanted_conditions in check.get("conditions", {}).items():
    result = results.get(int(key))
    conditions = [item.condition for item in result.conditions] if result is not None else []
    for wanted in wanted_conditions:
      tally.check("condition", any(_matches(condition, wanted) for condition in conditions),
                  f"line {key}: no condition matching {wanted}")

  if "evidence" in check:
    _evidence(session, facts, answers, product, check["evidence"], tally)


def _answered(answers: ClaimAnswers, question: NextQuestion, value: str) -> ClaimAnswers:
  line = question.line_index if question.line_index is not None else 0
  if question.slot == Slot.COVER_START_DATE:
    update: dict[str, object] = {"cover_start_date": date.fromisoformat(value)}
  elif question.slot == Slot.HAS_REFERRAL:
    update = {"has_referral": value == "yes"}
  elif question.slot == Slot.SERVICE_DATE:
    update = {"service_dates": {**answers.service_dates, line: date.fromisoformat(value)}}
  elif question.slot == Slot.SERVICE_DESCRIPTION:
    update = {"service_descriptions": {**answers.service_descriptions, line: value}}
  elif question.slot == Slot.BENEFITS_USED:
    update = {"benefits_used": {**answers.benefits_used, line: Decimal(value)}}
  elif question.slot == Slot.AMOUNT_PAID:
    update = {"amounts_paid": {**answers.amounts_paid, line: Decimal(value)}}
  else:
    raise ValueError(f"The script cannot answer {question.slot.value}.")
  return ClaimAnswers.model_validate({**answers.model_dump(), **update})


def _matches(condition: Condition, wanted: dict[str, str]) -> bool:
  if condition.kind.value != wanted["kind"]:
    return False
  for name in ("percent", "amount", "months"):
    if name in wanted:
      actual = getattr(condition, name)
      if actual is None or Decimal(str(actual)) != Decimal(wanted[name]):
        return False
  return True


def _evidence(
  session: Session,
  facts: ReceiptFacts,
  answers: ClaimAnswers,
  product: PolicyProduct,
  expected: dict[str, dict[str, list[str]]],
  tally: Tally,
) -> None:
  """Stage 3 recall: each labelled section must be among the passages a line's reading saw."""
  lines = {line.line_index: line for line in effective_lines(facts, answers)}
  queries = []
  for key in expected:
    line = lines[int(key)]
    document = document_for(product, line.service_date) if line.service_date else None
    if document is None:
      tally.check("evidence", False, f"line {key} has no policy edition to search")
      continue
    queries.append(ServiceQuery(
      line_index=line.line_index,
      document_id=document.id,
      scope=product.scope,
      service_text=service.service_text(line, facts),
    ))
  found = retrieve_evidence(session, service.get_claims_operations().embed, queries)
  for evidence in found:
    names = {
      name
      for chunk in evidence.chunks().values()
      for name in (chunk.section_number, chunk.section_title)
      if name
    }
    for aspect, sections in expected[str(evidence.line_index)].items():
      for section in sections:
        tally.check(f"evidence: {aspect}", section in names,
                    f"line {evidence.line_index}: {section} was not retrieved")


if __name__ == "__main__":
  raise SystemExit(main())
