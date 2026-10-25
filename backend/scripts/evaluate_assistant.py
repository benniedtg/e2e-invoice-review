from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

if __package__ in {None, ""}:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assistant import DocumentAssistant, DocumentQuery, QueryIntent  # noqa: E402
from app.config import load_azure_openai_settings  # noqa: E402
from app.providers import AzureOpenAIProvider  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "samples" / "assistant_questions.json"
REFERENCE_DATE = date(2026, 8, 15)
"""A fixed "today", so relative periods in the labelled questions resolve the same way."""
_UNORDERED_FIELDS = frozenset({"statuses", "document_types", "gl_account_codes", "issue_codes"})
_DECIMAL_FIELDS = frozenset({"min_total", "max_total"})


def main() -> int:
  parser = argparse.ArgumentParser(
    description=(
      "Evaluate the review-history question planner against labelled questions. "
      "Makes one billable Azure OpenAI call per question."
    ),
  )
  parser.parse_args()
  entries = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
  assistant = DocumentAssistant(AzureOpenAIProvider(load_azure_openai_settings()))
  defaults = DocumentQuery(intent=QueryIntent.SEARCH).model_dump(mode="json")
  matches = 0
  provider_failures = 0

  print(f"Evaluating {len(entries)} labelled questions (one Azure OpenAI call each)\n")
  for entry in entries:
    question = entry["question"]
    expected = {**defaults, **entry["expected"]}
    try:
      actual = assistant.plan(question, REFERENCE_DATE).model_dump(mode="json")
    except Exception as error:  # noqa: BLE001 - report all paid-operation failures
      provider_failures += 1
      print(f"FAIL  {question}\n      provider error: {error}")
      continue

    # An unsupported question carries no filter worth comparing.
    names = ("intent",) if expected["intent"] == QueryIntent.UNSUPPORTED else tuple(expected)
    mismatches = [name for name in names if not _same(name, expected[name], actual[name])]
    matches += not mismatches
    print(f"{'FAIL' if mismatches else 'PASS'}  {question}")
    for name in mismatches:
      print(f"      {name}: expected {expected[name]!r}, got {actual[name]!r}")

  print("\nSummary")
  print(f"  Planner matches:   {matches}/{len(entries)}")
  print(f"  Provider failures: {provider_failures}/{len(entries)}")
  return 1 if provider_failures > 0 or matches != len(entries) else 0


def _same(name: str, expected: object, actual: object) -> bool:
  """Compare one filter while tolerating order and harmless formatting differences."""
  if name in _UNORDERED_FIELDS and isinstance(expected, list) and isinstance(actual, list):
    return sorted(map(str, expected)) == sorted(map(str, actual))
  if name in _DECIMAL_FIELDS and expected is not None and actual is not None:
    try:
      return Decimal(str(expected)) == Decimal(str(actual))
    except InvalidOperation:
      return False
  if name == "vendor_text" and isinstance(expected, str) and isinstance(actual, str):
    return " ".join(expected.casefold().split()) == " ".join(actual.casefold().split())
  return expected == actual


if __name__ == "__main__":
  raise SystemExit(main())
