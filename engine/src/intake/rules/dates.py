"""DAT rules: policy dates that do not parse, run backwards, or disagree with status."""

import polars as pl

from agency_schema.enums import Family, PolicyStatus, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import parse_date_loose
from agency_schema.registry import rule
from intake.rules.frames import MA_PDP, hit, norm, policy_rows, shown

DATE_FIELDS = ("effective_date", "termination_date")


@rule("DAT-001", Severity.ERROR, Family.DAT, "Effective (or termination) date unparseable")
def date_unparseable(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit("DAT-001", r, f, r[f], f'"{shown(r[f])}" is not a date', "Correct the date")
        for r in policy_rows(frame)
        for f in DATE_FIELDS
        if r[f] and parse_date_loose(r[f]) is None
    ]


@rule("DAT-002", Severity.ERROR, Family.DAT, "Termination before effective")
def term_before_effective(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in policy_rows(frame):
        start = parse_date_loose(r["effective_date"] or "")
        end = parse_date_loose(r["termination_date"] or "")
        if start and end and end < start:
            term, effective = shown(r["termination_date"]), shown(r["effective_date"])
            message = f"Term {term} precedes effective {effective}"
            out.append(
                hit(
                    "DAT-002",
                    r,
                    "termination_date",
                    r["termination_date"],
                    message,
                    "Correct the dates",
                )
            )
    return out


@rule("DAT-003", Severity.ERROR, Family.DAT, "Status ACTIVE but termination date in past")
def active_but_ended(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in policy_rows(frame):
        end = parse_date_loose(r["termination_date"] or "")
        if norm(r["status"]) == PolicyStatus.ACTIVE and end and end < r["as_of"]:
            message = f"Terminated on {shown(r['termination_date'])} yet marked active"
            out.append(hit("DAT-003", r, "status", r["status"], message, "Update status"))
    return out


@rule("DAT-004", Severity.INFO, Family.DAT, "MA or PDP effective date not the first of a month")
def effective_mid_month(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in policy_rows(frame):
        start = parse_date_loose(r["effective_date"] or "")
        if start and start.day != 1 and norm(r["line_of_business"]) in MA_PDP:
            message = f"Effective {shown(r['effective_date'])} is not the 1st"
            out.append(
                hit(
                    "DAT-004",
                    r,
                    "effective_date",
                    r["effective_date"],
                    message,
                    "Usually a keying error",
                )
            )
    return out
