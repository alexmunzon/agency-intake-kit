"""check_run_dir: validate a whole run directory, each file and how the files agree.

Used by the sample-run tests now and by the end-to-end tests on real runs (PR 12), so the
engine and the dashboard read the same contract.
"""

from collections import Counter
from pathlib import Path
from typing import Any

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import (
    RUN_FILE_MODELS,
    LegResult,
    Manifest,
    RtsCellState,
    RtsCoverage,
    RunStatus,
    Scorecard,
    TieOutLeg,
    Totals,
    VarianceReport,
)


def _fail(message: str) -> None:
    raise ValueError(message)


def check_run_dir(run: Path) -> None:
    """Raise ValueError (or ValidationError) unless every run file is valid and consistent."""
    files: dict[str, Any] = {
        name: model.model_validate_json((run / name).read_text())
        for name, model in RUN_FILE_MODELS.items()
    }
    lines = (run / "exceptions.jsonl").read_text().splitlines()
    records = {r.id: r for r in map(ExceptionRecord.model_validate_json, filter(None, lines))}
    if len(records) != len([line for line in lines if line]):
        _fail("exception ids must be unique")

    manifest: Manifest = files["manifest.json"]
    card: Scorecard = files["scorecard.json"]
    if (manifest.run_id, manifest.status) != (card.run_id, card.status):
        _fail("manifest and scorecard disagree on run_id or status")
    by_severity = Counter(r.severity.value.lower() for r in records.values())
    counts = card.exceptions_by_severity.model_dump()
    if counts != {level: by_severity[level] for level in counts}:
        _fail("scorecard severity counts do not match exceptions.jsonl")
    if card.exceptions_by_rule != dict(Counter(r.rule_id for r in records.values())):
        _fail("scorecard rule counts do not match exceptions.jsonl")

    legs: list[LegResult] = [files[f"tie_out/leg_{s}.json"] for s in TieOutLeg.file_stems()]
    if [leg.model_dump(exclude={"variances"}) for leg in legs] != [
        summary.model_dump() for summary in card.tie_out
    ]:
        _fail("scorecard tie_out does not match the leg files")
    report: VarianceReport = files["tie_out/variances.json"]
    in_legs = sorted(v.model_dump_json() for leg in legs for v in leg.variances)
    if in_legs != sorted(v.model_dump_json() for v in report.variances if v.leg is not None):
        _fail("variances.json and the leg files list different leg variances")
    for v in report.variances:
        record = records.get(v.exception_id)
        if record is None or record.rule_id != v.rule_id:
            _fail(f"variance {v.exception_id} has no matching {v.rule_id} exception")

    for group in ("carrier", "agent"):
        totals: Totals = files[f"tie_out/totals_by_{group}.json"]
        if totals.group_by != group:
            _fail(f"totals_by_{group}.json is grouped by {totals.group_by}")

    coverage: RtsCoverage = files["rts_coverage.json"]
    gaps = [c for c in coverage.cells if c.coverage == RtsCellState.USED_WITHOUT_RTS]
    if card.rts_gaps != len(gaps):
        _fail("scorecard rts_gaps does not match rts_coverage.json")
    for ex_id in (ex_id for cell in gaps for ex_id in cell.exception_ids):
        if ex_id not in records or records[ex_id].rule_id != "RTS-001":
            _fail(f"RTS cell points at {ex_id}, which is not an RTS-001 exception")

    if card.status == RunStatus.FAILED and (run / "clean").exists():
        _fail("a FAILED run must not write clean/")
