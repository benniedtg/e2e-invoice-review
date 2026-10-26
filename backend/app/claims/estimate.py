"""Benefit arithmetic from verified policy conditions only. The model never computes amounts."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.claims.schemas import BenefitEstimate, Condition, ConditionKind, RateBasis

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(amount: Decimal) -> str:
  """Format an Australian-dollar amount the way a receipt prints it."""
  return f"${amount.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def percent(value: Decimal) -> str:
  """Format a percentage without trailing zeros."""
  return f"{value.normalize():f}%"


def estimate_benefit(
  amount_paid: Decimal,
  conditions: Sequence[Condition],
  benefits_used: Decimal | None,
) -> BenefitEstimate:
  """Apply rate, then per-service cap, then remaining annual limit, never above the amount paid."""
  rates = [
    condition
    for condition in conditions
    if condition.kind == ConditionKind.BENEFIT_RATE
    and condition.applies
    and condition.percent is not None
  ]
  rate = next(
    (condition for condition in rates if condition.basis == RateBasis.AMOUNT_CHARGED),
    None,
  )
  if rate is None or rate.percent is None:
    schedule_rate = next(
      (condition for condition in rates if condition.basis == RateBasis.MBS_FEE),
      None,
    )
    if schedule_rate is not None and schedule_rate.percent is not None:
      return BenefitEstimate(
        amount=None,
        steps=(),
        note=(
          f"The policy pays {percent(schedule_rate.percent)} of the Medicare Benefits "
          "Schedule fee for this service, not of the amount charged. MBS fees are not "
          "loaded, so no amount is estimated."
        ),
      )
    return BenefitEstimate(
      amount=None,
      steps=(),
      note="The policy text found does not say what share of the charge is paid.",
    )

  benefit = amount_paid * rate.percent / HUNDRED
  steps = [f"{percent(rate.percent)} of {money(amount_paid)} = {money(benefit)}"]
  for limit in _amounts(conditions, ConditionKind.PER_SERVICE_LIMIT):
    if benefit > limit:
      benefit = limit
      steps.append(f"capped at the per-service limit of {money(limit)}")
  for limit in _amounts(conditions, ConditionKind.ANNUAL_LIMIT):
    used = benefits_used or Decimal("0")
    remaining = max(limit - used, Decimal("0"))
    steps.append(
      f"annual limit {money(limit)} minus {money(used)} already paid = "
      f"{money(remaining)} remaining"
    )
    if benefit > remaining:
      benefit = remaining
      steps.append(f"capped at the {money(remaining)} remaining")
  benefit = min(benefit, amount_paid).quantize(CENT, rounding=ROUND_HALF_UP)
  steps.append(f"estimated benefit {money(benefit)}")
  return BenefitEstimate(amount=benefit, steps=tuple(steps))


def _amounts(conditions: Sequence[Condition], kind: ConditionKind) -> list[Decimal]:
  return [
    condition.amount
    for condition in conditions
    if condition.kind == kind and condition.applies and condition.amount is not None
  ]
