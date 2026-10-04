"""CON rules: email and phone that cannot be normalized."""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import normalize_email, normalize_phone
from agency_schema.registry import rule
from intake.rules.frames import client_rows, hit, shown


@rule("CON-001", Severity.WARNING, Family.CON, "Email syntax invalid")
def email_syntax(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "CON-001",
            r,
            "email",
            r["email"],
            f'"{shown(r["email"])}" is not an email',
            "Correct or clear",
        )
        for r in client_rows(frame)
        if r["email"] and normalize_email(r["email"]) is None
    ]


@rule("CON-002", Severity.WARNING, Family.CON, "Phone cannot be normalized to 10 digits")
def phone_digits(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "CON-002",
            r,
            "phone",
            r["phone"],
            f'"{shown(r["phone"])}" is not a phone',
            "Correct or clear",
        )
        for r in client_rows(frame)
        if r["phone"] and normalize_phone(r["phone"]) is None
    ]
