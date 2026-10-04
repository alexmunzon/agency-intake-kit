"""Row-level rules (PR 8): DOB, MBI, NPN, PLN, ADR, CON, DAT, STA.

Importing this package registers the rules. Each rule is pure: it reads one frame (see
frames.py) and returns ExceptionRecords. No rule calls Jev.
"""

import polars as pl

from agency_schema.enums import Family
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import run_rules
from intake.rules import address, contact, dates, dob, ids, status  # noqa: F401  (registers)

ROW_FAMILIES = frozenset(
    {Family.DOB, Family.MBI, Family.NPN, Family.PLN, Family.ADR, Family.CON, Family.DAT, Family.STA}
)


def run_row_rules(clients: pl.DataFrame, policies: pl.DataFrame) -> list[ExceptionRecord]:
    """Every row rule on the client frame, then on the policy frame, in rule id order."""
    return [
        record
        for frame in (clients, policies)
        for family in sorted(ROW_FAMILIES)
        for record in run_rules(frame, family=family)
    ]
