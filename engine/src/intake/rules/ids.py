"""MBI, NPN, and plan ID rules."""

import polars as pl

from agency_schema.enums import Family, LineOfBusiness, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import (
    is_valid_hios_plan_id,
    is_valid_mbi,
    is_valid_medigap_letter,
    is_valid_npn,
    parse_medicare_plan_id,
)
from agency_schema.registry import rule
from intake.rules.frames import MA_PDP, MEDICARE, client_rows, hit, norm, policy_rows, shown


@rule("MBI-001", Severity.ERROR, Family.MBI, "MBI format invalid")
def mbi_format(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "MBI-001",
            r,
            "mbi",
            r["mbi"],
            f'"{shown(r["mbi"])}" fails the MBI pattern',
            "Re-key from the Medicare card",
        )
        for r in client_rows(frame)
        if r["mbi"] and not is_valid_mbi(r["mbi"])
    ]


@rule("MBI-002", Severity.WARNING, Family.MBI, "MBI present on a non-Medicare policy")
def mbi_on_aca(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "MBI-002",
            r,
            "mbi",
            r["client_mbi"],
            f"MBI on ACA policy {r['policy_id']}",
            "Remove or confirm",
            lineage="client_lineage",
            extra=r["policy_id"],
        )
        for r in policy_rows(frame)
        if r["client_lineage"] and r["client_mbi"] and norm(r["line_of_business"]) == "ACA"
    ]


@rule("MBI-003", Severity.WARNING, Family.MBI, "Medicare policy missing MBI")
def mbi_missing(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """Reported on the client row (where the MBI lives), once per Medicare policy."""
    return [
        hit(
            "MBI-003",
            r,
            "mbi",
            None,
            f"No MBI on {r['policy_id']}",
            "Obtain from client",
            lineage="client_lineage",
            extra=r["policy_id"],
        )
        for r in policy_rows(frame)
        if r["client_lineage"] and not r["client_mbi"] and norm(r["line_of_business"]) in MEDICARE
    ]


@rule("NPN-001", Severity.ERROR, Family.NPN, "NPN not 1 to 10 digits")
def npn_format(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "NPN-001",
            r,
            "writing_agent_npn",
            npn,
            f'"{shown(npn)}" is not a valid NPN',
            "Correct from NIPR",
        )
        for r in policy_rows(frame)
        if (npn := r["writing_agent_npn"]) and not is_valid_npn(npn)
    ]


@rule("NPN-002", Severity.ERROR, Family.NPN, "Writing agent not in roster")
def npn_unknown(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """A malformed NPN is NPN-001's job, so it is not reported here twice."""
    return [
        hit(
            "NPN-002",
            r,
            "writing_agent_npn",
            npn,
            f"NPN {shown(npn)} unknown",
            "Add agent to roster or fix NPN",
        )
        for r in policy_rows(frame)
        if (npn := r["writing_agent_npn"]) and is_valid_npn(npn) and not r["agent_in_roster"]
    ]


def _plan_rows(frame: pl.DataFrame, lines: frozenset[str]) -> list[dict[str, str]]:
    return [r for r in policy_rows(frame) if r["plan_id"] and norm(r["line_of_business"]) in lines]


@rule("PLN-001", Severity.ERROR, Family.PLN, "Medicare plan ID malformed (MA and PDP only)")
def plan_medicare_format(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "PLN-001",
            r,
            "plan_id",
            r["plan_id"],
            f'"{shown(r["plan_id"])}" is not H/R/S####-###(-###)',
            "Correct the plan ID",
        )
        for r in _plan_rows(frame, MA_PDP)
        if parse_medicare_plan_id(r["plan_id"]) is None
    ]


@rule("PLN-002", Severity.ERROR, Family.PLN, "HIOS plan ID malformed (ACA only)")
def plan_hios_format(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "PLN-002",
            r,
            "plan_id",
            r["plan_id"],
            f'"{shown(r["plan_id"])}" is not a 14-character HIOS id',
            "Correct the plan ID",
        )
        for r in _plan_rows(frame, frozenset({LineOfBusiness.ACA}))
        if not is_valid_hios_plan_id(r["plan_id"])
    ]


@rule(
    "PLN-003",
    Severity.ERROR,
    Family.PLN,
    "Plan ID prefix disagrees with line of business (MA and PDP only)",
)
def plan_prefix_lob(frame: pl.DataFrame) -> list[ExceptionRecord]:
    out = []
    for r in _plan_rows(frame, MA_PDP):
        parsed = parse_medicare_plan_id(r["plan_id"])
        lob = norm(r["line_of_business"])
        if parsed and parsed.line_of_business != lob:
            message = f"{parsed.prefix}-prefix plan ID on a policy marked {lob}"
            out.append(
                hit("PLN-003", r, "plan_id", r["plan_id"], message, "Correct LOB or plan ID")
            )
    return out


@rule("PLN-004", Severity.ERROR, Family.PLN, "Medigap plan letter invalid (MEDSUPP only)")
def plan_medigap_letter(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "PLN-004",
            r,
            "plan_id",
            r["plan_id"],
            f'"{shown(r["plan_id"])}" is not a Medigap plan A to N',
            "Correct the plan letter",
        )
        for r in _plan_rows(frame, frozenset({LineOfBusiness.MEDSUPP}))
        if not is_valid_medigap_letter(r["plan_id"])
    ]
