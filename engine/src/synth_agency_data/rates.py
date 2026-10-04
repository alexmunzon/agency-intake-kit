"""Illustrative monthly commission amounts for the synthetic world.

These are made up for testing. They are NOT CMS maximum compensation amounts and not any
carrier's real schedule. Tie-out (PR 10) checks statement amounts against this table.
"""

from datetime import date
from decimal import Decimal

from agency_schema.enums import CommissionType, LineOfBusiness

# A policy pays NEW for its first 12 months in force, RENEWAL after that.
NEW_BUSINESS_MONTHS = 12

MONTHLY_RATES: dict[tuple[LineOfBusiness, CommissionType], Decimal] = {
    (LineOfBusiness.MA, CommissionType.NEW): Decimal("52.50"),
    (LineOfBusiness.MA, CommissionType.RENEWAL): Decimal("26.25"),
    (LineOfBusiness.PDP, CommissionType.NEW): Decimal("8.40"),
    (LineOfBusiness.PDP, CommissionType.RENEWAL): Decimal("4.20"),
    (LineOfBusiness.MEDSUPP, CommissionType.NEW): Decimal("38.00"),
    (LineOfBusiness.MEDSUPP, CommissionType.RENEWAL): Decimal("19.00"),
    (LineOfBusiness.ACA, CommissionType.NEW): Decimal("22.00"),
    (LineOfBusiness.ACA, CommissionType.RENEWAL): Decimal("16.00"),
}


def commission_type(effective: date, period: str) -> CommissionType:
    """NEW while the policy is in its first 12 months at the statement period (YYYY-MM)."""
    year, month = (int(part) for part in period.split("-"))
    months_in_force = (year - effective.year) * 12 + month - effective.month
    return CommissionType.NEW if months_in_force < NEW_BUSINESS_MONTHS else CommissionType.RENEWAL


def expected_amount(line_of_business: str, effective: date, period: str) -> Decimal:
    return MONTHLY_RATES[(LineOfBusiness(line_of_business), commission_type(effective, period))]
