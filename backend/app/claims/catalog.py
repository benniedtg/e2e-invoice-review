"""Fixed OSHC catalog: the insurers, products, and policy editions the checker knows.

Policy files are public but copyrighted, so they are downloaded into the gitignored
data/policies/ directory and ingested locally instead of being committed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType

from app.documents.database import DATA_DIRECTORY

POLICY_DIRECTORY = DATA_DIRECTORY / "policies"


class DocumentLayout(StrEnum):
  """How one policy document numbers its sections and marks product scopes."""

  NIB_FUND_RULES = "nib_fund_rules"
  BUPA_FUND_RULES = "bupa_fund_rules"
  ALLIANZ_MEMBERS_GUIDE = "allianz_members_guide"


@dataclass(frozen=True, slots=True)
class Insurer:
  """One OSHC insurer a student can name."""

  id: str
  name: str


@dataclass(frozen=True, slots=True)
class PolicyDocument:
  """One edition of an insurer's binding policy text and the dates it governs."""

  id: str
  insurer_id: str
  title: str
  source_url: str
  file_name: str
  layout: DocumentLayout
  effective_from: date | None
  effective_to: date | None
  effective_basis: str

  def governs(self, service_date: date) -> bool:
    """Report whether this edition applies to a service on that date."""
    starts = self.effective_from is None or self.effective_from <= service_date
    ends = self.effective_to is None or service_date <= self.effective_to
    return starts and ends


@dataclass(frozen=True, slots=True)
class PolicyProduct:
  """One OSHC product a student can hold, and where its terms are written."""

  id: str
  insurer_id: str
  name: str
  scope: str | None
  """Section scope inside a document several products share; None is the whole document."""
  document_ids: tuple[str, ...]


INSURERS = (
  Insurer("nib", "nib OSHC"),
  Insurer("bupa", "Bupa OSHC"),
  Insurer("allianz", "Allianz Care OSHC"),
)

_NIB_RULES = "nib-oshc-fund-rules-2026-07-29"
_BUPA_RULES = "bupa-oshc-rules-2026-06-30"
_ALLIANZ_STANDARD_CURRENT = "allianz-oshc-standard-2026-07-01"
_ALLIANZ_STANDARD_PREVIOUS = "allianz-oshc-standard-2025-09-03"
_ALLIANZ_ESSENTIALS = "allianz-oshc-essentials-2025-09-03"

POLICY_DOCUMENTS = (
  PolicyDocument(
    id=_NIB_RULES,
    insurer_id="nib",
    title="nib Fund Rules: Overseas Students Health Cover (29 July 2026)",
    source_url="https://www.nib.com.au/docs/oshc-fund-rules",
    file_name="nib-oshc-fund-rules/nib-oshc-fund-rules.pdf",
    layout=DocumentLayout.NIB_FUND_RULES,
    effective_from=date(2026, 7, 29),
    effective_to=None,
    effective_basis="Dated 29 July 2026 on its cover.",
  ),
  PolicyDocument(
    id=_BUPA_RULES,
    insurer_id="bupa",
    title="Bupa Overseas Student Health Cover Rules (effective 30 June 2026)",
    source_url="https://www.bupa.com.au/-/media/dotcom/files/pdfs/oshc-fund-rules.pdf",
    file_name="bupa-oshc-fund-rules/bupa-oshc-fund-rules.pdf",
    layout=DocumentLayout.BUPA_FUND_RULES,
    effective_from=date(2026, 6, 30),
    effective_to=None,
    effective_basis="Stated on page 1: Effective 30 June 2026.",
  ),
  PolicyDocument(
    id=_ALLIANZ_STANDARD_CURRENT,
    insurer_id="allianz",
    title="Allianz Care OSHC Standard: policy document and members guide (1 July 2026)",
    source_url=(
      "https://www.allianzcare.com.au/content/dam/onemarketing/azpau/allianzcare/docs/"
      "policy/IMP3731_0726_AllianzCare_OSHC_Standard.pdf"
    ),
    file_name="allianz-oshc-standard-current/allianz-oshc-standard.pdf",
    layout=DocumentLayout.ALLIANZ_MEMBERS_GUIDE,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    effective_basis="Stated on its cover: Effective 1 July 2026.",
  ),
  PolicyDocument(
    id=_ALLIANZ_STANDARD_PREVIOUS,
    insurer_id="allianz",
    title="Allianz Care OSHC Standard: policy document and members guide (previous edition)",
    source_url=(
      "https://www.allianzcare.com.au/content/dam/onemarketing/azpau/allianzcare/docs/"
      "policy/IMP3731_OSHC_Standard_Policy.pdf"
    ),
    file_name="allianz-oshc-standard-previous/allianz-oshc-standard.pdf",
    layout=DocumentLayout.ALLIANZ_MEMBERS_GUIDE,
    effective_from=date(2025, 9, 3),
    effective_to=date(2026, 6, 30),
    effective_basis=(
      "No date stated; the PDF was produced on 3 September 2025 and the 1 July 2026 "
      "edition replaced it."
    ),
  ),
  PolicyDocument(
    id=_ALLIANZ_ESSENTIALS,
    insurer_id="allianz",
    title="Allianz Care OSHC Essentials: policy document and members guide",
    source_url=(
      "https://www.allianzcare.com.au/content/dam/onemarketing/azpau/allianzcare/docs/"
      "policy/IMP3730_OSHC_Essentials_Policy.pdf"
    ),
    file_name="allianz-oshc-essentials/allianz-oshc-essentials.pdf",
    layout=DocumentLayout.ALLIANZ_MEMBERS_GUIDE,
    effective_from=date(2025, 9, 3),
    effective_to=date(2026, 6, 30),
    effective_basis=(
      "No date stated; the PDF was produced on 3 September 2025. Treated as replaced on "
      "1 July 2026 like the Standard edition, because no newer Essentials edition is loaded."
    ),
  ),
)

POLICY_PRODUCTS = (
  PolicyProduct("nib-core", "nib", "nib OSHC Core", "LS4", (_NIB_RULES,)),
  PolicyProduct("nib-premium", "nib", "nib OSHC Premium", "LS6", (_NIB_RULES,)),
  PolicyProduct("nib-top", "nib", "nib OSHC Top Cover", "LS9", (_NIB_RULES,)),
  PolicyProduct("nib-ultimate", "nib", "nib OSHC Ultimate", "LS11", (_NIB_RULES,)),
  PolicyProduct("nib-student-care", "nib", "nib OSHC Student Care", "LS12", (_NIB_RULES,)),
  PolicyProduct("bupa-oshc", "bupa", "Bupa Overseas Student Health Cover", "P1", (_BUPA_RULES,)),
  PolicyProduct(
    "bupa-advantage",
    "bupa",
    "Bupa Advantage Overseas Student Health Cover",
    "P2",
    (_BUPA_RULES,),
  ),
  PolicyProduct(
    "bupa-success",
    "bupa",
    "Bupa Success Overseas Student Health Cover",
    "P3",
    (_BUPA_RULES,),
  ),
  PolicyProduct(
    "allianz-essentials",
    "allianz",
    "Allianz Care OSHC Essentials",
    None,
    (_ALLIANZ_ESSENTIALS,),
  ),
  PolicyProduct(
    "allianz-standard",
    "allianz",
    "Allianz Care OSHC Standard",
    None,
    (_ALLIANZ_STANDARD_CURRENT, _ALLIANZ_STANDARD_PREVIOUS),
  ),
)

INSURERS_BY_ID = MappingProxyType({insurer.id: insurer for insurer in INSURERS})
DOCUMENTS_BY_ID = MappingProxyType({document.id: document for document in POLICY_DOCUMENTS})
PRODUCTS_BY_ID = MappingProxyType({product.id: product for product in POLICY_PRODUCTS})

if (
  len(INSURERS_BY_ID) != len(INSURERS)
  or len(DOCUMENTS_BY_ID) != len(POLICY_DOCUMENTS)
  or len(PRODUCTS_BY_ID) != len(POLICY_PRODUCTS)
):
  raise RuntimeError("The OSHC catalog contains duplicate identifiers.")
for _product in POLICY_PRODUCTS:
  if _product.insurer_id not in INSURERS_BY_ID or any(
    DOCUMENTS_BY_ID.get(document_id) is None
    or DOCUMENTS_BY_ID[document_id].insurer_id != _product.insurer_id
    for document_id in _product.document_ids
  ):
    raise RuntimeError(f"OSHC product {_product.id} references an unknown policy.")


def products_for(insurer_id: str) -> tuple[PolicyProduct, ...]:
  """List one insurer's products in catalog order."""
  return tuple(product for product in POLICY_PRODUCTS if product.insurer_id == insurer_id)


def document_for(product: PolicyProduct, service_date: date) -> PolicyDocument | None:
  """Pick the edition of a product's terms that governs a service date, if loaded."""
  for document_id in product.document_ids:
    document = DOCUMENTS_BY_ID[document_id]
    if document.governs(service_date):
      return document
  return None
