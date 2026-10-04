"""Output model rules: each case breaks exactly one rule in a valid sample file."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agency_schema.outputs import RUN_FILE_MODELS

FIXTURES = Path(__file__).parents[3] / "fixtures"
LEG_A = "tie_out/leg_book_vs_statement.json"
LEG_B = "tie_out/leg_statement_vs_book.json"
LEG_C = "tie_out/leg_crm_vs_statement.json"
CARRIERS = "tie_out/totals_by_carrier.json"
COUNTS = ["matched", "unmatched", "weak_matched", "variance_count", "variance_dollars"]
NOT_RUN_SUMMARY = {"status": "NOT_RUN", "not_run_reason": "No CRM file in the drop"}
NOT_RUN_SUMMARY.update(dict.fromkeys(COUNTS))
NOT_RUN = {"status": "NOT_RUN", "not_run_reason": "No CRM file in the drop", "variances": []}


def first_variance(d: dict[str, Any], **change: Any) -> dict[str, Any]:
    return {**d, "variances": [{**d["variances"][0], **change}, *d["variances"][1:]]}


def first_cell(d: dict[str, Any], **change: Any) -> dict[str, Any]:
    gap = next(c for c in d["cells"] if c["coverage"] == "USED_WITHOUT_RTS")
    return {"cells": [{**gap, **change}]}


CASES: list[tuple[str, str, str, Any]] = [
    ("not run leg with counts", "sample-run", LEG_C, lambda d: {**d, **NOT_RUN}),
    ("ran leg missing a count", "sample-run", LEG_A, lambda d: {**d, "matched": None}),
    ("weak matches beyond matched", "sample-run", LEG_A, lambda d: {**d, "weak_matched": 9999}),
    ("variance count off", "sample-run", LEG_B, lambda d: {**d, "variance_count": 2}),
    ("variance dollars off", "sample-run", LEG_B, lambda d: {**d, "variance_dollars": "0.01"}),
    (
        "difference not paid minus expected",
        "sample-run",
        LEG_B,
        lambda d: first_variance(d, difference="1.00"),
    ),
    ("rule in the wrong leg", "sample-run", LEG_B, lambda d: first_variance(d, rule_id="TIE-001")),
    (
        "totals difference off",
        "sample-run",
        CARRIERS,
        lambda d: {**d, "rows": [{**d["rows"][0], "difference": "999.99"}]},
    ),
    ("duplicate totals key", "sample-run", CARRIERS, lambda d: {**d, "rows": d["rows"][:1] * 2}),
    (
        "totals not run without reason",
        "sample-run-failed",
        CARRIERS,
        lambda d: {**d, "not_run_reason": None},
    ),
    ("PASSED with warnings", "sample-run", "scorecard.json", lambda d: {**d, "status": "PASSED"}),
    (
        "FAILED without a blocker",
        "sample-run",
        "scorecard.json",
        lambda d: {**d, "status": "FAILED", "rows_clean": 0},
    ),
    (
        "FAILED with clean rows",
        "sample-run-failed",
        "scorecard.json",
        lambda d: {**d, "rows_mapped": 5, "rows_clean": 5},
    ),
    (
        "PASSED with a leg not run",
        "sample-run-passed",
        "scorecard.json",
        lambda d: {**d, "tie_out": [*d["tie_out"][:2], {**d["tie_out"][2], **NOT_RUN_SUMMARY}]},
    ),
    ("rows grow", "sample-run", "scorecard.json", lambda d: {**d, "rows_clean": d["rows_in"] + 1}),
    ("a leg missing", "sample-run", "scorecard.json", lambda d: {**d, "tie_out": d["tie_out"][:2]}),
    (
        "no reason when not PASSED",
        "sample-run",
        "manifest.json",
        lambda d: {**d, "status_reason": None},
    ),
    (
        "finished before started",
        "sample-run",
        "manifest.json",
        lambda d: {**d, "finished_at": "2026-10-01T08:59:59Z"},
    ),
    (
        "cost beyond six decimals",
        "sample-run",
        "manifest.json",
        lambda d: {**d, "jev": {**d["jev"], "estimated_cost_usd": "0.0000001"}},
    ),
    (
        "Jev off with calls",
        "sample-run",
        "manifest.json",
        lambda d: {**d, "jev": {**d["jev"], "mode": "off"}},
    ),
    (
        "gap without its exceptions",
        "sample-run",
        "rts_coverage.json",
        lambda d: first_cell(d, exception_ids=[]),
    ),
    (
        "gap policy count off",
        "sample-run",
        "rts_coverage.json",
        lambda d: first_cell(d, policy_count=5),
    ),
    (
        "held unused with policies",
        "sample-run",
        "rts_coverage.json",
        lambda d: first_cell(d, coverage="HELD_UNUSED"),
    ),
    (
        "duplicate RTS cell",
        "sample-run",
        "rts_coverage.json",
        lambda d: {"cells": d["cells"][:1] * 2},
    ),
    ("unknown field", "sample-run", "manifest.json", lambda d: {**d, "ssn": "x"}),
]


@pytest.mark.parametrize(("why", "sample", "name", "edit"), CASES, ids=[c[0] for c in CASES])
def test_model_refuses(why: str, sample: str, name: str, edit: Any) -> None:
    data = json.loads((FIXTURES / sample / name).read_text())
    RUN_FILE_MODELS[name].model_validate(data)  # the untouched file is valid
    with pytest.raises(ValidationError):
        RUN_FILE_MODELS[name].model_validate(edit(data))
