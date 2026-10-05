"""The blocking policy: run status, blocks_load, rows kept out of clean/, lanes, and fixes.

Severity decides, never Jev. Exactly three blockers (MAP-003, CMP-001, SSN-001) fail the run.
Errors keep their rows out of clean/ and warnings pass with a flag; either one makes the run
PASSED_WITH_WARNINGS. Info is logged only.
"""

from collections.abc import Iterable

from agency_schema.enums import Lane, Severity
from agency_schema.exceptions import BLOCKER_RULE_IDS, ExceptionRecord
from agency_schema.outputs import RunStatus

# Suggested fixes from BUILD-GUIDE section 6, used when a stage left suggested_fix blank.
CATALOG_FIXES = {
    "ING-004": "Confirm delimiter",
    "MAP-001": "Map manually in the mapping file for this source",
    "MAP-002": "Confirm or correct the mapping",
    "MAP-003": "Add the column or map an existing one",
    "SSN-001": "Remove the column before intake",
    "CMP-001": "Re-export the file; check for truncation",
    "CMP-002": "Supply the file; its tie-out leg is marked not run",
    "DUP-001": "Drop one",
    "DUP-002": "Resolve (handled fully in bob-resolve)",
    "DUP-003": "Keep the correct row",
    "REF-001": "Add client or fix client_id",
    "RTS-001": "Obtain RTS or reassign writing agent",
    "RTS-002": "Renew RTS",
    "LIC-001": "Verify license",
    "TIE-001": "Check carrier statement or policy status",
    "TIE-002": "Add policy or investigate",
    "TIE-003": "Check commission type or rate",
    "TIE-004": "Update CRM",
    "TIE-005": "Investigate legs A and B",
    "TIE-006": "Add carrier_member_id to CRM",
    "PII-001": "Keep notes out of exports",
}

# Lanes set before triage. Errors and warnings stay UNREVIEWED until triage routes them.
_LANE_BEFORE_TRIAGE = {Severity.BLOCKER: Lane.REVIEW, Severity.INFO: Lane.UNREVIEWED}


def blocks_load(rule_id: str) -> bool:
    return rule_id in BLOCKER_RULE_IDS


def run_status(records: Iterable[ExceptionRecord]) -> RunStatus:
    severities = {r.severity for r in records}
    if Severity.BLOCKER in severities:
        return RunStatus.FAILED
    if severities & {Severity.ERROR, Severity.WARNING}:
        return RunStatus.PASSED_WITH_WARNINGS
    return RunStatus.PASSED


def excluded_rows(records: Iterable[ExceptionRecord]) -> set[tuple[str, int]]:
    """(source, row_number) of every row an error keeps out of clean/."""
    return {
        (r.source, r.row_number)
        for r in records
        if r.severity == Severity.ERROR and r.row_number is not None
    }


def apply_policy(records: Iterable[ExceptionRecord]) -> list[ExceptionRecord]:
    """Fill blank fixes from the catalog and set the lanes triage does not decide.

    blocks_load needs no work here: ExceptionRecord refuses any record where it disagrees
    with the three blockers.
    """
    out = []
    for r in records:
        update = {
            "suggested_fix": r.suggested_fix or CATALOG_FIXES.get(r.rule_id),
            "lane": _LANE_BEFORE_TRIAGE.get(r.severity, r.lane),
        }
        out.append(ExceptionRecord.model_validate({**r.model_dump(), **update}))
    return out
