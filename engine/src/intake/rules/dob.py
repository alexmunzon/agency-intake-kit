"""DOB rules: birth dates that do not parse, impossible ages, and under-65 Medicare."""

import polars as pl

from agency_schema.enums import EligibilityReason, Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import parse_date_loose
from agency_schema.registry import rule
from intake.config import DOB_MAX_AGE, DOB_MIN_AGE, MEDICARE_AGE
from intake.rules.frames import MEDICARE, age_on, client_rows, hit, norm, policy_rows, shown

DISABLED = {EligibilityReason.DISABILITY, EligibilityReason.ESRD}


@rule("DOB-001", Severity.ERROR, Family.DOB, "DOB unparseable")
def dob_unparseable(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit("DOB-001", r, "dob", r["dob"], f'"{shown(r["dob"])}" is not a date', "Correct the date")
        for r in client_rows(frame)
        if r["dob"] and parse_date_loose(r["dob"]) is None
    ]


@rule("DOB-002", Severity.ERROR, Family.DOB, "Age outside 0 to 115 (a future DOB counts)")
def dob_age_range(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in client_rows(frame):
        born = parse_date_loose(r["dob"] or "")
        if born and not DOB_MIN_AGE <= (age := age_on(born, r["as_of"])) <= DOB_MAX_AGE:
            message = f"DOB {shown(r['dob'])} gives age {age}"
            out.append(hit("DOB-002", r, "dob", r["dob"], message, "Check for a century error"))
    return out


@rule(
    "DOB-003",
    Severity.WARNING,
    Family.DOB,
    "Medicare policy, age under 65 at effective date, eligibility_reason not DISABILITY or ESRD",
)
def dob_under_65_medicare(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in policy_rows(frame):
        born = parse_date_loose(r["client_dob"] or "")
        start = parse_date_loose(r["effective_date"] or "")
        if (
            born
            and start
            and norm(r["line_of_business"]) in MEDICARE
            and norm(r["eligibility_reason"]) not in DISABLED
            and age_on(born, start) < MEDICARE_AGE
        ):
            out.append(
                hit(
                    "DOB-003",
                    r,
                    "eligibility_reason",
                    r["eligibility_reason"],
                    "Under-65 Medicare enrollee",
                    "Confirm disability or ESRD eligibility",
                )
            )
    return out
