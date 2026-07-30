from __future__ import annotations

from openai import OpenAI, OpenAIError

from app.config import AzureOpenAISettings

AZURE_OPENAI_MODEL = "gpt-5.6-terra"


class AzureOpenAIError(Exception):
  """A safe user-facing Azure OpenAI failure."""


def _base_url(settings: AzureOpenAISettings) -> str:
  endpoint = str(settings.endpoint).rstrip("/")
  if settings.endpoint.path.rstrip("/") != "/openai/v1":
    endpoint = f"{endpoint}/openai/v1"
  return f"{endpoint}/"


def generate_text(prompt: str, settings: AzureOpenAISettings) -> str:
  """Generate one text response through the Azure OpenAI Responses API."""
  try:
    with OpenAI(
      base_url=_base_url(settings),
      api_key=settings.api_key.get_secret_value(),
    ) as client:
      response = client.responses.create(
        model=AZURE_OPENAI_MODEL,
        input=prompt,
        store=False,
      )
  except OpenAIError:
    raise AzureOpenAIError("Azure OpenAI request failed.") from None

  answer = response.output_text.strip()
  if not answer:
    raise AzureOpenAIError("Azure OpenAI returned no text output.")
  return answer
