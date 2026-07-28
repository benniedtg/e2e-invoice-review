from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
  """Financial document types supported by the learning surface."""

  INVOICE = "invoice"
  RECEIPT = "receipt"


class StrictSchema(BaseModel):
  """Base configuration shared by normalized document schemas."""

  model_config = ConfigDict(extra="forbid")


class ExtractedField[T](StrictSchema):
  """A normalized value with its provider evidence."""

  value: T
  content: str | None = None
  confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Money(StrictSchema):
  """A decimal monetary amount and its reported currency."""

  amount: Decimal
  currency_code: str | None = None
  currency_symbol: str | None = None
