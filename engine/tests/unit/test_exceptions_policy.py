"""The blocking policy (PR 11): status, rows kept out of clean/, lanes, and fixes."""

import json
from pathlib import Path
from typing import Any

import pytest

from agency_schema.enums import Lane
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import RunStatus
from intake.exceptions.policy import apply_policy, blocks_load, excluded_rows, run_status

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def make(base: dict[str, Any], rule_id: str, severity: str, **extra: Any) -> ExceptionRecord:
    kwargs = {**base, "rule_id": rule_id, "family": rule_id[:3], "severity": severity}
    kwargs["blocks_load"] = severity == "BLOCKER"
    if rule_id[:3] in {"CMP", "MAP", "SSN"}:
        kwargs.update(row_number=None, raw_hash=None, lineage=None, field=None)
        kwargs["value_minimized"] = None
    return ExceptionRecord.model_validate({**kwargs, **extra})


@pytest.mark.parametrize("sample", ["sample-run", "sample-run-failed", "sample-run-passed"])
def test_policy_reproduces_each_sample_run_status(sample: str) -> None:
    folder = FIXTURES / sample
    lines = (folder / "exceptions.jsonl").read_text().splitlines()
    records = [ExceptionRecord.model_validate_json(line) for line in lines if line]
    expected = json.loads((folder / "manifest.json").read_text())["status"]
    assert run_status(records) == RunStatus(expected)


@pytest.mark.parametrize(
    ("severities", "status"),
    [
        ([], RunStatus.PASSED),
        (["INFO"], RunStatus.PASSED),
        (["WARNING", "INFO"], RunStatus.PASSED_WITH_WARNINGS),
        (["ERROR"], RunStatus.PASSED_WITH_WARNINGS),
        (["ERROR", "WARNING", "BLOCKER"], RunStatus.FAILED),
    ],
)
def test_status_from_synthetic_lists(
    exception_kwargs: dict[str, Any], severities: list[str], status: RunStatus
) -> None:
    rules = {"INFO": "DAT-004", "WARNING": "CON-001", "ERROR": "DOB-001", "BLOCKER": "CMP-001"}
    records = [make(exception_kwargs, rules[s], s) for s in severities]
    assert run_status(records) == status


def test_exactly_three_rules_block() -> None:
    assert [
        r for r in ("MAP-003", "CMP-001", "SSN-001", "RTS-001", "TIE-002") if blocks_load(r)
    ] == [
        "MAP-003",
        "CMP-001",
        "SSN-001",
    ]


def test_errors_exclude_rows_and_warnings_do_not(exception_kwargs: dict[str, Any]) -> None:
    error = make(exception_kwargs, "DOB-001", "ERROR")
    warning = make(exception_kwargs, "CON-001", "WARNING", source="policies")
    blocker = make(exception_kwargs, "CMP-001", "BLOCKER")
    assert excluded_rows([error, warning, blocker]) == {("crm", 2)}


def test_lanes_and_catalog_fixes(exception_kwargs: dict[str, Any]) -> None:
    blocker = make(exception_kwargs, "CMP-001", "BLOCKER", suggested_fix=None)
    info = make(exception_kwargs, "DAT-004", "INFO", lane="REVIEW")
    error = make(exception_kwargs, "DOB-001", "ERROR")
    out = apply_policy([blocker, info, error])
    assert [r.lane for r in out] == [Lane.REVIEW, Lane.UNREVIEWED, Lane.UNREVIEWED]
    assert out[0].suggested_fix == "Re-export the file; check for truncation"
    assert out[2] == error
