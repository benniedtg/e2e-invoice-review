from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
if str(BACKEND_DIRECTORY) not in sys.path:
  sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.config import (  # noqa: E402
  ConfigurationError,
  load_document_intelligence_settings,
)
from app.providers.azure_document_intelligence import (  # noqa: E402
  DocumentIntelligenceError,
  DocumentMappingError,
  analyze_document,
  map_document,
)
from app.schemas import DocumentType, NormalizedDocument  # noqa: E402

JSON_OUTPUT_DIRECTORY = BACKEND_DIRECTORY / "json_extracted"
MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024
SUPPORTED_SUFFIXES = frozenset({".jpeg", ".jpg", ".pdf", ".png"})


class CliError(Exception):
  """An expected command-line failure with a safe user-facing message."""


def validate_document_path(path: Path) -> Path:
  """Resolve and validate one supported local financial document."""
  document_path = path.expanduser().resolve()
  if not document_path.exists():
    raise CliError(f"Document file does not exist: {path}")
  if not document_path.is_file():
    raise CliError(f"Document path is not a file: {path}")
  if document_path.suffix.lower() not in SUPPORTED_SUFFIXES:
    supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
    raise CliError(f"Unsupported document type; choose one of: {supported}")

  file_size = document_path.stat().st_size
  if file_size == 0:
    raise CliError(f"Document file is empty: {path}")
  if file_size > MAX_FILE_SIZE_BYTES:
    raise CliError("Document file exceeds the 4 MB limit.")
  return document_path


def raw_result_to_json(result: Mapping[str, Any]) -> str:
  """Serialize the complete Azure result as readable JSON."""
  return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def save_raw_result(document_path: Path, result: Mapping[str, Any]) -> Path:
  """Save the complete Azure result for provider observation."""
  JSON_OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
  output_path = JSON_OUTPUT_DIRECTORY / f"{document_path.stem}.json"
  output_path.write_text(f"{raw_result_to_json(result)}\n", encoding="utf-8")
  return output_path


def save_normalized_result(
  document_path: Path,
  result: NormalizedDocument,
) -> Path:
  """Save the normalized Pydantic document beside the raw result."""
  JSON_OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
  output_path = JSON_OUTPUT_DIRECTORY / f"{document_path.stem}.normalized.json"
  output_path.write_text(f"{result.model_dump_json(indent=2)}\n", encoding="utf-8")
  return output_path


def build_parser() -> argparse.ArgumentParser:
  """Create the command-line argument parser."""
  parser = argparse.ArgumentParser(
    description="Analyze one invoice or receipt with Azure Document Intelligence."
  )
  parser.add_argument(
    "--document-type",
    type=DocumentType,
    choices=list(DocumentType),
    default=DocumentType.INVOICE,
    help="Azure prebuilt model to use (default: invoice)",
  )
  parser.add_argument(
    "document",
    type=Path,
    help="Path to a PDF, PNG, JPG, or JPEG invoice or receipt",
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Run financial-document analysis and normalization."""
  args = build_parser().parse_args(argv)
  try:
    document_path = validate_document_path(args.document)
    settings = load_document_intelligence_settings()
    raw_result = analyze_document(document_path, args.document_type, settings)
    raw_output_path = save_raw_result(document_path, raw_result)
  except (CliError, ConfigurationError, DocumentIntelligenceError, OSError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1

  try:
    normalized_result = map_document(raw_result, args.document_type)
    normalized_output_path = save_normalized_result(document_path, normalized_result)
  except DocumentMappingError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    print(f"Raw extraction saved to {raw_output_path}", file=sys.stderr)
    return 1
  except OSError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1

  print(f"Saved raw extraction to {raw_output_path}")
  print(f"Saved normalized document to {normalized_output_path}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
