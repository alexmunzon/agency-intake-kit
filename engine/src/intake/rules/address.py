"""ADR rules: ZIP shape, ZIP prefix against state, and state codes."""

import re

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import ZIP_PATTERN, zip3_matches_state, zip3_table
from agency_schema.registry import rule
from intake.rules.frames import client_rows, hit, norm, raw, shown


def _zip5(value: str) -> str | None:
    """The 5-digit ZIP from 12345, 12345-6789, or 123456789. None if it is none of those."""
    text = value.strip()
    if ZIP_PATTERN.fullmatch(text) or re.fullmatch(r"\d{9}", text):
        return text[:5]
    return None


def _is_state(value: str) -> bool:
    return any(norm(value) in states for states in zip3_table().values())


@rule("ADR-001", Severity.ERROR, Family.ADR, "ZIP not 5 or 9 digits")
def zip_format(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit("ADR-001", r, "zip", r["zip"], f'"{shown(r["zip"])}" is not a ZIP', "Correct the ZIP")
        for r in client_rows(frame)
        if r["zip"] and _zip5(r["zip"]) is None
    ]


@rule("ADR-002", Severity.ERROR, Family.ADR, "ZIP prefix inconsistent with state")
def zip_state(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in client_rows(frame):
        zip5 = _zip5(r["zip"] or "")
        state = r["state"] or ""
        if zip5 and _is_state(state) and not zip3_matches_state(zip5, state):
            message = f"ZIP {shown(r['zip'])} is not in {norm(state)}"
            out.append(hit("ADR-002", r, "zip", r["zip"], message, "Correct ZIP or state"))
    return out


@rule("ADR-003", Severity.ERROR, Family.ADR, "State code invalid")
def state_code(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """Judged on the state as written, even when the word table or Jev normalized it."""
    return [
        hit(
            "ADR-003",
            r,
            "state",
            raw(r, "state"),
            f'"{shown(raw(r, "state"))}" is not a state',
            "Correct the state",
        )
        for r in client_rows(frame)
        if raw(r, "state") and not _is_state(raw(r, "state") or "")
    ]
