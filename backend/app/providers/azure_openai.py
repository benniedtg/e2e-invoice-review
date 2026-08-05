from __future__ import annotations

import asyncio

from azure.core.exceptions import ClientAuthenticationError
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent, NativeOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.openai import (
  OpenAIResponsesModel,
  OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider

from app.config import AzureOpenAISettings

AZURE_OPENAI_MODEL = "gpt-5.6-terra"


class AzureOpenAIError(Exception):
  """A safe user-facing Azure OpenAI failure."""


class AzureOpenAIProvider:
  """Own Azure OpenAI configuration and provider-specific operations."""

  def __init__(self, settings: AzureOpenAISettings) -> None:
    endpoint = str(settings.endpoint).rstrip("/")
    endpoint_path = (settings.endpoint.path or "").rstrip("/")
    if endpoint_path != "/openai/v1":
      endpoint = f"{endpoint}/openai/v1"
    self._base_url = f"{endpoint}/"

  def generate_text(self, prompt: str) -> str:
    """Send one text prompt and return the generated text."""
    try:
      return asyncio.run(self._run_text(prompt))
    except (AgentRunError, OpenAIError, ClientAuthenticationError):
      raise AzureOpenAIError("Azure OpenAI request failed.") from None

  def analyze_document[StructuredOutput: BaseModel](
    self,
    *,
    document_bytes: bytes,
    mime_type: str,
    instructions: str,
    output_type: type[StructuredOutput],
  ) -> StructuredOutput:
    """Analyze document bytes and return the requested Pydantic model."""
    normalized_mime_type = mime_type.strip().lower()
    prompt: list[str | BinaryContent] = [
      instructions,
      BinaryContent(data=document_bytes, media_type=normalized_mime_type),
    ]
    try:
      return asyncio.run(
        self._run_structured(prompt=prompt, output_type=output_type)
      )
    except (AgentRunError, OpenAIError, ClientAuthenticationError):
      raise AzureOpenAIError("Azure OpenAI document analysis failed.") from None

  def generate_structured[StructuredOutput: BaseModel](
    self,
    *,
    prompt: str,
    output_type: type[StructuredOutput],
  ) -> StructuredOutput:
    """Generate one strict Pydantic output from text or JSON-only input."""
    try:
      return asyncio.run(
        self._run_structured(prompt=prompt, output_type=output_type)
      )
    except (AgentRunError, OpenAIError, ClientAuthenticationError):
      raise AzureOpenAIError("Azure OpenAI structured generation failed.") from None

  def _model(
    self,
    client: AsyncOpenAI,
  ) -> OpenAIResponsesModel:
    """Build a stateless Responses model around one operation-scoped client."""
    provider = PydanticOpenAIProvider(openai_client=client)
    return OpenAIResponsesModel(
      AZURE_OPENAI_MODEL,
      provider=provider,
      settings=OpenAIResponsesModelSettings(openai_store=False),
    )

  async def _run_text(self, prompt: str) -> str:
    """Run one text request inside closed Entra and OpenAI client scopes."""
    async with DefaultAzureCredential() as credential:
      token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
      )
      async with AsyncOpenAI(
        base_url=self._base_url,
        api_key=token_provider,
      ) as client:
        result = await Agent(self._model(client)).run(prompt)
        answer = str(result.output).strip()
        if not answer:
          raise AzureOpenAIError("Azure OpenAI returned no text output.")
        return answer

  async def _run_structured[StructuredOutput: BaseModel](
    self,
    *,
    prompt: str | list[str | BinaryContent],
    output_type: type[StructuredOutput],
  ) -> StructuredOutput:
    """Run one strict request inside closed Entra and OpenAI client scopes."""
    async with DefaultAzureCredential() as credential:
      token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
      )
      async with AsyncOpenAI(
        base_url=self._base_url,
        api_key=token_provider,
      ) as client:
        model = self._model(client)
        agent = Agent(
          model,
          output_type=NativeOutput(output_type, strict=True),
        )
        return (await agent.run(prompt)).output
