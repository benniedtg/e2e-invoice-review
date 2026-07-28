from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIRECTORY / ".env"
INVOICE_MODEL_ID = "prebuilt-invoice"
MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024
SUPPORTED_SUFFIXES = frozenset({".jpeg", ".jpg", ".pdf", ".png"})


class CliError(Exception):
  """An expected command-line failure with a safe user-facing message."""


class DocumentIntelligenceSettings(BaseSettings):
  """Credentials required for the Document Intelligence learning surface."""

  model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
  )

  endpoint: str = Field(
    min_length=1,
    validation_alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
  )
  key: SecretStr = Field(
    min_length=1,
    validation_alias="AZURE_DOCUMENT_INTELLIGENCE_KEY",
  )


def load_settings() -> DocumentIntelligenceSettings:
  """Load Document Intelligence credentials without exposing validation details."""
  try:
    return DocumentIntelligenceSettings()
  except ValidationError:
    raise CliError(
      "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
      "AZURE_DOCUMENT_INTELLIGENCE_KEY in backend/.env."
    ) from None


def validate_invoice_path(path: Path) -> Path:
  """Resolve and validate one supported local invoice file."""
  invoice_path = path.expanduser().resolve()
  if not invoice_path.exists():
    raise CliError(f"Invoice file does not exist: {path}")
  if not invoice_path.is_file():
    raise CliError(f"Invoice path is not a file: {path}")
  if invoice_path.suffix.lower() not in SUPPORTED_SUFFIXES:
    supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
    raise CliError(f"Unsupported invoice type; choose one of: {supported}")

  file_size = invoice_path.stat().st_size
  if file_size == 0:
    raise CliError(f"Invoice file is empty: {path}")
  if file_size > MAX_FILE_SIZE_BYTES:
    raise CliError("Invoice file exceeds the 4 MB limit.")
  return invoice_path


def analyze_invoice(
  invoice_path: Path,
  settings: DocumentIntelligenceSettings,
) -> AnalyzeResult:
  """Submit one local invoice to Azure's prebuilt invoice model."""
  credential = AzureKeyCredential(settings.key.get_secret_value())
  with DocumentIntelligenceClient(
    endpoint=settings.endpoint,
    credential=credential,
  ) as client:
    with invoice_path.open("rb") as invoice:
      poller = client.begin_analyze_document(INVOICE_MODEL_ID, body=invoice)
      return poller.result()


def result_to_json(result: AnalyzeResult) -> str:
  """Serialize the complete Azure result as readable JSON."""
  return json.dumps(result.as_dict(), indent=2, ensure_ascii=False, default=str)


def build_parser() -> argparse.ArgumentParser:
  """Create the command-line argument parser."""
  parser = argparse.ArgumentParser(
    description="Analyze one local invoice with Azure Document Intelligence."
  )
  parser.add_argument("invoice", type=Path, help="Path to a PDF, PNG, JPG, or JPEG invoice")
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Run the invoice analysis command."""
  args = build_parser().parse_args(argv)
  try:
    invoice_path = validate_invoice_path(args.invoice)
    settings = load_settings()
    result = analyze_invoice(invoice_path, settings)
  except (AzureError, CliError, OSError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1

  print(result_to_json(result))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
