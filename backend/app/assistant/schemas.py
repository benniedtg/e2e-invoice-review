from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import ConfigDict, Field, model_validator

from app.accounting import resolve_general_ledger_account
from app.documents.models import ReviewStatus
from app.invoices import ValidationIssueCode
from app.schemas import DocumentType
from app.schemas.common import StrictSchema


class QueryIntent(StrEnum):
  """Whether the stored reviews can answer a question at all."""

  SEARCH = "search"
  UNSUPPORTED = "unsupported"


class QueryAggregate(StrEnum):
  """What a question wants from the matching documents."""

  LIST = "list"
  COUNT = "count"
  TOTAL = "total"


class QueryGroup(StrEnum):
  """How counts and totals are broken down."""

  NONE = "none"
  GL_ACCOUNT = "gl_account"
  VENDOR = "vendor"
  STATUS = "status"
  DOCUMENT_TYPE = "document_type"


class DocumentQuery(StrictSchema):
  """A typed filter over stored reviews. The model proposes it; local rules check it."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  intent: QueryIntent
  statuses: tuple[ReviewStatus, ...] = ()
  document_types: tuple[DocumentType, ...] = ()
  vendor_text: str | None = Field(default=None, max_length=100)
  date_from: date | None = None
  date_to: date | None = None
  gl_account_codes: tuple[Annotated[str, Field(pattern=r"^\d{4}$")], ...] = ()
  min_total: Decimal | None = None
  max_total: Decimal | None = None
  has_errors: bool | None = None
  issue_codes: tuple[ValidationIssueCode, ...] = ()
  is_duplicate: bool | None = None
  used_llm_fallback: bool | None = None
  aggregate: QueryAggregate = QueryAggregate.LIST
  group_by: QueryGroup = QueryGroup.NONE

  @model_validator(mode="after")
  def validate_filters(self) -> DocumentQuery:
    """Reject inverted ranges and accounts outside the fixed Northstar catalog."""
    if (
      self.date_from is not None
      and self.date_to is not None
      and self.date_from > self.date_to
    ):
      raise ValueError("date_from cannot be after date_to.")
    if (
      self.min_total is not None
      and self.max_total is not None
      and self.min_total > self.max_total
    ):
      raise ValueError("min_total cannot exceed max_total.")
    for account_code in self.gl_account_codes:
      resolve_general_ledger_account(account_code)
    return self


class AssistantAnswer(StrictSchema):
  """One plain-text answer and the stored documents it relies on."""

  model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

  answer: str = Field(min_length=1, max_length=2000)
  cited_document_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentGroupTotal:
  """How many matching documents share one group and currency, and their total."""

  group: str | None
  currency: str | None
  document_count: int
  total_cents: int | None
  documents_without_total: int
