from __future__ import annotations

from pathlib import Path

from pydantic import AnyUrl, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIRECTORY / ".env"


class ConfigurationError(Exception):
  """A safe user-facing configuration failure."""


class DocumentIntelligenceSettings(BaseSettings):
  """Credentials required for Azure Document Intelligence."""

  model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
  )

  endpoint: AnyUrl = Field(
    validation_alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
  )
  key: SecretStr = Field(
    min_length=1,
    validation_alias="AZURE_DOCUMENT_INTELLIGENCE_KEY",
  )

  @field_validator("endpoint")
  @classmethod
  def require_https_endpoint(cls, endpoint: AnyUrl) -> AnyUrl:
    """Accept only well-formed HTTPS provider endpoints."""
    if endpoint.scheme != "https":
      raise ValueError("Document Intelligence endpoint must use HTTPS.")
    return endpoint


def load_document_intelligence_settings() -> DocumentIntelligenceSettings:
  """Load Document Intelligence credentials without exposing validation details."""
  try:
    # BaseSettings supplies these required fields from .env at runtime.
    return DocumentIntelligenceSettings()  # pyright: ignore[reportCallIssue]
  except ValidationError:
    raise ConfigurationError(
      "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
      "AZURE_DOCUMENT_INTELLIGENCE_KEY in backend/.env."
    ) from None


class AzureOpenAISettings(BaseSettings):
  """Credentials required for Azure OpenAI."""

  model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
  )

  endpoint: AnyUrl = Field(
    validation_alias="AZURE_OPENAI_ENDPOINT",
  )
  api_key: SecretStr = Field(
    min_length=1,
    validation_alias="AZURE_OPENAI_API_KEY",
  )

  @field_validator("endpoint")
  @classmethod
  def require_responses_endpoint(cls, endpoint: AnyUrl) -> AnyUrl:
    """Accept supported HTTPS Azure OpenAI and Foundry endpoints."""
    if endpoint.scheme != "https":
      raise ValueError("Azure OpenAI endpoint must use HTTPS.")
    if endpoint.query is not None or endpoint.fragment is not None:
      raise ValueError("Azure OpenAI endpoint cannot contain a query or fragment.")

    endpoint_path = endpoint.path.rstrip("/")
    project_name = endpoint_path.removeprefix("/api/projects/")
    is_project_endpoint = (
      project_name != endpoint_path
      and bool(project_name)
      and "/" not in project_name
    )
    if endpoint_path not in {"", "/openai/v1"} and not is_project_endpoint:
      raise ValueError(
        "Azure OpenAI endpoint must be a resource root, a Foundry project "
        "endpoint, or end with /openai/v1/."
      )
    return endpoint


def load_azure_openai_settings() -> AzureOpenAISettings:
  """Load Azure OpenAI credentials without exposing validation details."""
  try:
    # BaseSettings supplies these required fields from .env at runtime.
    return AzureOpenAISettings()  # pyright: ignore[reportCallIssue]
  except ValidationError:
    raise ConfigurationError(
      "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY in backend/.env."
    ) from None
