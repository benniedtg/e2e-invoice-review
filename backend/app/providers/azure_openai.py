from __future__ import annotations

import asyncio
from collections.abc import Sequence
from urllib.parse import urlsplit

from azure.core.exceptions import ClientAuthenticationError
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent, Embedder, NativeOutput
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.openai import (
  OpenAIResponsesModel,
  OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider

from app.config import AzureOpenAISettings

AZURE_OPENAI_MODEL = "gpt-5.6-terra"
AZURE_OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"

EMBEDDING_BATCH_SIZE = 64
"""Inputs per embeddings request, well inside the service's per-request limits."""

CREDENTIAL_PROCESS_TIMEOUT = 60
"""Seconds a local developer credential may take. Azure CLI often needs more than
the SDK's 10-second default to hand out a token, which fails every call; managed
identity in a deployment does not run a subprocess and is unaffected."""


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
    # A Foundry project endpoint serves the Responses API but not embeddings, and the
    # services.ai.azure.com host refuses embeddings to the Cognitive Services OpenAI
    # User role, so embeddings use the same account's openai.azure.com host.
    account = (urlsplit(str(settings.endpoint)).hostname or "").split(".")[0]
    self._embeddings_base_url = f"https://{account}.openai.azure.com/openai/v1/"

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

  def embed(self, texts: Sequence[str]) -> list[list[float]]:
    """Embed texts in order, batching requests, and return one vector per text."""
    try:
      return asyncio.run(self._run_embeddings(list(texts)))
    except (AgentRunError, OpenAIError, ClientAuthenticationError):
      raise AzureOpenAIError("Azure OpenAI embedding request failed.") from None

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
    async with DefaultAzureCredential(
      process_timeout=CREDENTIAL_PROCESS_TIMEOUT,
    ) as credential:
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
    async with DefaultAzureCredential(
      process_timeout=CREDENTIAL_PROCESS_TIMEOUT,
    ) as credential:
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

  async def _run_embeddings(self, texts: list[str]) -> list[list[float]]:
    """Embed every batch inside one closed Entra and OpenAI client scope."""
    async with DefaultAzureCredential(
      process_timeout=CREDENTIAL_PROCESS_TIMEOUT,
    ) as credential:
      token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
      )
      async with AsyncOpenAI(
        base_url=self._embeddings_base_url,
        api_key=token_provider,
      ) as client:
        embedder = Embedder(
          OpenAIEmbeddingModel(
            AZURE_OPENAI_EMBEDDING_MODEL,
            provider=PydanticOpenAIProvider(openai_client=client),
          )
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
          batch = texts[start : start + EMBEDDING_BATCH_SIZE]
          result = await embedder.embed_documents(batch)
          vectors.extend(list(vector) for vector in result.embeddings)
        return vectors
