from pydantic import ConfigDict, Field

from app.schemas.common import StrictSchema


class CorrectionEmailDraft(StrictSchema):
  """A strict copyable draft that the application never sends or stores."""

  model_config = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    str_strip_whitespace=True,
  )

  recipient_name: str = Field(min_length=1, max_length=200)
  subject: str = Field(min_length=1, max_length=200)
  body: str = Field(min_length=1, max_length=4000)
