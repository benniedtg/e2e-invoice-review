from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import AnyUrl, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIRECTORY / ".env"


@dataclass(frozen=True, slots=True)
class NorthstarPolicy:
  """Fixed fictional finance policy used by deterministic validation."""

  customer_name: str
  customer_vat_id: str
  minimum_primary_confidence: float


NORTHSTAR_POLICY = NorthstarPolicy(
  customer_name="Northstar Facilities B.V.",
  customer_vat_id="NL00449544B01",
  minimum_primary_confidence=0.80,
)


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
  """Endpoint required for Entra-authenticated Azure OpenAI."""

  model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
  )

  endpoint: AnyUrl = Field(
    validation_alias="AZURE_OPENAI_ENDPOINT",
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
      "Set AZURE_OPENAI_ENDPOINT in backend/.env and authenticate locally with "
      "Azure CLI or another DefaultAzureCredential source."
    ) from None


class ApiSettings(BaseSettings):
  """Local API settings that all have working defaults."""

  model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
  )

  # Kept as raw text because pydantic-settings JSON-decodes collection fields.
  cors_allowed_origins: str = Field(
    default="http://localhost:5173",
    validation_alias="CORS_ALLOWED_ORIGINS",
  )

  @property
  def allowed_origins(self) -> tuple[str, ...]:
    """Split the configured comma-separated browser origins."""
    return tuple(
      origin.strip()
      for origin in self.cors_allowed_origins.split(",")
      if origin.strip()
    )


def load_api_settings() -> ApiSettings:
  """Load API settings, which never require a populated backend/.env."""
  return ApiSettings()
