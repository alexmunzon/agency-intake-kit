"""Per-run usage accounting and the spend estimate. The price comes from config.py."""

from decimal import ROUND_HALF_UP, Decimal

from agency_schema.lineage import StrictModel
from agency_schema.outputs import Count, JevMode, UsdCost
from intake.config import JEV_USD_PER_MTOK_IN

_MICRO = Decimal("0.000001")


def estimate_cost_usd(input_tokens: int) -> Decimal:
    """An estimate, not a bill: input tokens times the published price. Output is free."""
    raw = Decimal(input_tokens) * JEV_USD_PER_MTOK_IN / Decimal(1_000_000)
    return raw.quantize(_MICRO, rounding=ROUND_HALF_UP)


class RunUsage(StrictModel):
    """What one run used. PR 12 copies the counts into the manifest's JevUsage.

    `mode` stays the configured mode even after a budget trip; `budget_tripped` records
    that the rest of the run was sent to the human queue.
    """

    mode: JevMode
    calls: Count
    input_tokens: Count
    output_tokens: Count
    estimated_cost_usd: UsdCost
    budget_usd: UsdCost
    budget_tripped: bool
