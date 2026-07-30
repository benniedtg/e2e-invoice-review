from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
if str(BACKEND_DIRECTORY) not in sys.path:
  sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.config import ConfigurationError, load_azure_openai_settings  # noqa: E402
from app.providers.azure_openai import (  # noqa: E402
  AzureOpenAIError,
  generate_text,
)


class CliError(Exception):
  """An expected command-line failure with a safe user-facing message."""


def validate_prompt(prompt: str) -> str:
  """Return a non-empty prompt without surrounding whitespace."""
  cleaned_prompt = prompt.strip()
  if not cleaned_prompt:
    raise CliError("Prompt cannot be empty.")
  return cleaned_prompt


def build_parser() -> argparse.ArgumentParser:
  """Create the command-line argument parser."""
  parser = argparse.ArgumentParser(
    description="Send one text prompt to Azure OpenAI."
  )
  parser.add_argument(
    "prompt",
    help="Text prompt to send to the hard-coded Azure OpenAI deployment",
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Send one prompt and print its text response."""
  args = build_parser().parse_args(argv)
  try:
    prompt = validate_prompt(args.prompt)
    settings = load_azure_openai_settings()
    answer = generate_text(prompt, settings)
  except (CliError, ConfigurationError, AzureOpenAIError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1

  print(f"answer: {answer}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
