"""The six canonical tables.

No field has a default. A field that may be blank is typed `X | None` and must still be
passed explicitly, so a forgotten column fails loudly instead of becoming a silent blank.
Format validity (MBI, ZIP, plan IDs) is decided by rules, which emit ExceptionRecords.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt

from agency_schema.enums import (
    AgentStatus,
    CommissionType,
    EligibilityReason,
    LineOfBusiness,
    PolicyStatus,
)
from agency_schema.lineage import Lineage, NonEmpty, OptionalText, RowNumber, StrictModel

# Exact to the cent. Floats would make tie-out tolerance checks flaky.
Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


class Client(StrictModel):
    client_id: NonEmpty
    first_name: NonEmpty
    last_name: NonEmpty
    dob: date
    phone: OptionalText
    email: OptionalText
    address_line1: NonEmpty
    city: NonEmpty
    state: NonEmpty
    zip: NonEmpty
    mbi: OptionalText
    household_id: OptionalText
    notes: OptionalText  # free text: must pass the PII gate before any log or model call
    lineage: Lineage


class Household(StrictModel):
    household_id: NonEmpty
    primary_client_id: NonEmpty
    members: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]  # client_ids
    lineage: Lineage


class Agent(StrictModel):
    npn: NonEmpty
    first_name: NonEmpty
    last_name: NonEmpty
    email: OptionalText
    license_states: tuple[NonEmpty, ...]
    upline_npn: OptionalText
    status: AgentStatus
    lineage: Lineage


class Rts(StrictModel):
    """Ready-to-sell status. Key: (npn, carrier, state, plan_year, line_of_business)."""

    npn: NonEmpty
    carrier: NonEmpty
    state: NonEmpty
    plan_year: StrictInt
    line_of_business: LineOfBusiness
    appointed: StrictBool
    certified: StrictBool
    effective_date: date
    end_date: date | None
    lineage: Lineage


class Policy(StrictModel):
    policy_id: NonEmpty
    client_id: NonEmpty
    carrier: NonEmpty
    plan_id: NonEmpty  # Medicare contract-plan ID, Medigap letter, or HIOS ID by line of business
    line_of_business: LineOfBusiness
    state: OptionalText  # None falls back to the client's address state
    eligibility_reason: EligibilityReason | None  # None for ACA
    effective_date: date
    termination_date: date | None
    status: PolicyStatus
    writing_agent_npn: NonEmpty
    monthly_premium: Money | None
    carrier_member_id: OptionalText
    lineage: Lineage


class CommissionLine(StrictModel):
    """Key: (carrier, statement_period, line_no)."""

    carrier: NonEmpty
    statement_period: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]  # YYYY-MM
    line_no: RowNumber
    carrier_member_id: OptionalText
    member_name: OptionalText
    member_dob: date | None
    policy_ref: OptionalText
    agent_npn: OptionalText
    amount: Money  # negative for chargebacks
    commission_type: CommissionType
    paid_date: date | None
    lineage: Lineage


TABLE_MODELS: dict[str, type[StrictModel]] = {
    "clients": Client,
    "households": Household,
    "agents": Agent,
    "rts": Rts,
    "policies": Policy,
    "commission_lines": CommissionLine,
}
