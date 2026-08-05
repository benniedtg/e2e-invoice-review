"""Fixed Northstar general-ledger accounts and local selection validation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


class GeneralLedgerCatalogError(ValueError):
  """A model-selected account code is not in Northstar's fixed catalog."""


@dataclass(frozen=True, slots=True)
class GeneralLedgerAccount:
  """One immutable account available for a Northstar expense classification."""

  code: str
  name: str


GENERAL_LEDGER_CATALOG = (
  GeneralLedgerAccount("6100", "Cleaning Services"),
  GeneralLedgerAccount("6110", "Repairs and Maintenance"),
  GeneralLedgerAccount("6120", "Electrical Services"),
  GeneralLedgerAccount("6130", "Plumbing Services"),
  GeneralLedgerAccount("6140", "Grounds and Landscaping"),
  GeneralLedgerAccount("6150", "Lift and Safety Services"),
  GeneralLedgerAccount("6200", "Equipment Rental"),
  GeneralLedgerAccount("6210", "Tools and Equipment"),
  GeneralLedgerAccount("6300", "Fuel and Vehicle Expenses"),
  GeneralLedgerAccount("6400", "Office and Administrative Expenses"),
)
"""The complete, immutable Northstar GL catalog in prompt display order."""

_accounts_by_code = {account.code: account for account in GENERAL_LEDGER_CATALOG}
if len(_accounts_by_code) != len(GENERAL_LEDGER_CATALOG):
  raise RuntimeError("Northstar GL catalog contains duplicate account codes.")

GENERAL_LEDGER_ACCOUNTS_BY_CODE = MappingProxyType(_accounts_by_code)
"""Read-only account lookup used to validate every model selection locally."""


def resolve_general_ledger_account(account_code: str) -> GeneralLedgerAccount:
  """Return the canonical account for a known code or reject it locally."""
  try:
    return GENERAL_LEDGER_ACCOUNTS_BY_CODE[account_code]
  except KeyError:
    raise GeneralLedgerCatalogError(
      "Suggested GL account code is not in the Northstar catalog."
    ) from None
