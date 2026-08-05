from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import NORTHSTAR_POLICY, load_document_intelligence_settings  # noqa: E402
from app.invoices.validation import ValidationContext, validate_document  # noqa: E402
from app.providers.azure_document_intelligence import (  # noqa: E402
  AzureDocumentIntelligenceProvider,
)
from scripts.evaluation import (  # noqa: E402
  compare_fields,
  duplicate_code,
  load_manifest,
  policy_issue_codes,
  review_values,
  select_entries,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "samples" / "manifest.json"
SAMPLES_PATH = ROOT / "samples" / "generated"
MIME_TYPES = {
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
}


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Evaluate Document Intelligence against the fictional corpus labels.",
    epilog=(
      "Narrow duplicate check: 10-de-duplicate.pdf requires "
      "03-de-happy-modern.pdf; pass both explicitly."
    ),
  )
  parser.add_argument(
    "filenames",
    nargs="*",
    help=(
      "Optional manifest filenames for a narrow, paid check. Sample 10 requires "
      "sample 03 in the same selection."
    ),
  )
  arguments = parser.parse_args()
  entries = load_manifest(MANIFEST_PATH)
  try:
    entries = select_entries(entries, arguments.filenames)
  except ValueError as error:
    parser.error(str(error))

  provider = AzureDocumentIntelligenceProvider(load_document_intelligence_settings())
  seen_invoice_keys: set[tuple[str, str]] = set()
  matched_fields = 0
  total_fields = 0
  exact_documents = 0
  policy_matches = 0
  provider_failures = 0

  print(f"Evaluating {len(entries)} fictional financial documents\n")
  for entry in entries:
    path = SAMPLES_PATH / entry.filename
    try:
      _mime_type_for(path)
      document = provider.extract(path.read_bytes(), entry.document_type)
      comparison = compare_fields(entry.expected, review_values(document))
      report = validate_document(document, ValidationContext(
        policy=NORTHSTAR_POLICY,
        duplicate_code=duplicate_code(document, seen_invoice_keys),
      ))
    except Exception as error:  # noqa: BLE001 - report all provider failures
      provider_failures += 1
      print(f"FAIL  {entry.filename:<36} provider error: {error}")
      continue

    matched = sum(comparison.values())
    total = len(comparison)
    mismatches = [name for name, is_match in comparison.items() if not is_match]
    issue_codes = policy_issue_codes(report.issues)
    policy_ok = issue_codes == entry.expected_issue_codes
    matched_fields += matched
    total_fields += total
    exact_documents += not mismatches
    policy_matches += policy_ok
    detail = "all fields" if not mismatches else f"mismatch: {', '.join(mismatches)}"
    result = "PASS" if not mismatches else "PART"
    policy = "policy-ok" if policy_ok else (
      f"policy={list(issue_codes)} expected={list(entry.expected_issue_codes)}"
    )
    print(f"{result}  {entry.filename:<36} {matched:>2}/{total}  {detail}  {policy}")

  accuracy = (matched_fields / total_fields * 100) if total_fields else 0
  print("\nSummary")
  print(f"  Field accuracy:     {matched_fields}/{total_fields} ({accuracy:.1f}%)")
  print(f"  Exact documents:   {exact_documents}/{len(entries)}")
  print(f"  Policy matches:    {policy_matches}/{len(entries)}")
  print(f"  Provider failures: {provider_failures}/{len(entries)}")
  failed = (
    provider_failures > 0
    or exact_documents != len(entries)
    or policy_matches != len(entries)
  )
  return 1 if failed else 0


def _mime_type_for(path: Path) -> str:
  try:
    return MIME_TYPES[path.suffix.casefold()]
  except KeyError:
    raise ValueError(f"Unsupported sample suffix: {path.suffix}") from None


if __name__ == "__main__":
  raise SystemExit(main())
