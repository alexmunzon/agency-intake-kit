"""Write a run directory: manifest, scorecard, exceptions, tie-out, RTS coverage, clean/.

Every JSON file goes through its model, so the dashboard and check_run_dir read exactly what
the models allow. With a frozen clock two runs of the same drop write byte-identical files.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.lineage import StrictModel
from agency_schema.outputs import (
    DetectionSummary,
    InputFile,
    JevUsage,
    LegSummary,
    Manifest,
    RtsCellState,
    RtsCoverage,
    RunStatus,
    Scorecard,
    SeverityCounts,
)
from intake import __version__, config
from intake.ingest import IngestResult
from intake.readers import RawTable
from intake.run.clean import clean_row_count, clean_tables, write_clean
from intake.run.statement_totals import StatementTotals
from intake.run.unresolved_evidence import UnresolvedEvidence, serialize_unresolved_evidence
from intake.tieout import TieOutResult, write_tieout
from jev_client import RunUsage

THRESHOLDS = {
    "jev_budget_usd": float(config.JEV_BUDGET_USD),
    "map_auto_confidence": config.MAP_AUTO,
    "map_review_confidence": config.MAP_SUGGEST,
    "enum_auto_confidence": config.ENUM_AUTO,
    "pii_redact_probability": config.PII_REDACT,
    "tie_line_tolerance_pct": float(config.TIE_LINE_TOLERANCE_PCT),
    "tie_line_tolerance_usd": float(config.TIE_LINE_TOLERANCE_USD),
    "tie_total_tolerance_pct": float(config.TIE_TOTAL_TOLERANCE_PCT),
    "triage_business_event_max": config.TRIAGE_BUSINESS_EVENT,
    "triage_entry_error_min": config.TRIAGE_ENTRY_ERROR,
}


@dataclass(frozen=True)
class RunOutputs:
    run_id: str
    drop: Path
    started: datetime
    finished: datetime
    as_of: datetime | None
    ingest: IngestResult
    tables: dict[str, pl.DataFrame]
    records: list[ExceptionRecord]
    status: RunStatus
    tie: TieOutResult
    coverage: RtsCoverage
    usage: RunUsage
    detection: DetectionSummary | None
    unresolved: tuple[UnresolvedEvidence, ...] = ()
    statement_totals: StatementTotals | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(o: RunOutputs) -> tuple[InputFile, ...]:
    """One entry per file that arrived, in drop/manifest.json order. The roster's two sheets
    add up into one entry, because the dashboard shows one card per file."""
    by_file: dict[str, list[RawTable]] = {}
    for t in o.ingest.tables:
        by_file.setdefault(t.source_file, []).append(t)
    out = []
    for file_name, tables in by_file.items():
        expected = [t.expected_rows if t.expected_rows is not None else t.total_row_count
                    for t in tables]  # fmt: skip
        out.append(
            InputFile(
                source=tables[0].source,
                file_name=file_name,
                sha256=sha256_file(o.drop / file_name),
                rows_expected=None if None in expected else sum(e or 0 for e in expected),
                rows_received=sum(t.rows for t in tables),
            )
        )
    return tuple(out)


def status_reason(status: RunStatus, records: list[ExceptionRecord]) -> str | None:
    """One plain sentence for the banner. FAILED names the first blocker and its counts."""
    counts = Counter(r.severity for r in records)
    if status == RunStatus.FAILED:
        first = next(r for r in records if r.severity == Severity.BLOCKER)
        return f"Blocked by {first.rule_id}. {first.message.rstrip('.')}. Nothing was loaded."
    if status == RunStatus.PASSED:
        return None
    return (
        f"No blockers. {counts[Severity.ERROR]:,} errors keep their rows out of the load files "
        f"and {counts[Severity.WARNING]:,} warnings pass with a flag."
    )


def manifest(o: RunOutputs) -> Manifest:
    u = o.usage
    return Manifest(
        run_id=o.run_id,
        started_at=o.started,
        finished_at=o.finished,
        as_of=o.as_of,
        engine_version=__version__,
        status=o.status,
        status_reason=status_reason(o.status, o.records),
        inputs=inputs(o),
        jev=JevUsage(
            mode=u.mode,
            calls=u.calls,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            estimated_cost_usd=u.estimated_cost_usd,
        ),
        budget_tripped=u.budget_tripped,
        thresholds=THRESHOLDS,
    )


def mapped_rows(tables: dict[str, pl.DataFrame]) -> int:
    """Distinct source rows that reached a canonical table."""
    units = [
        frame.select(pl.col("lineage").struct.field("source_file", "sheet", "row_number"))
        for frame in tables.values()
    ]
    return pl.concat(units).unique().height if units else 0


def scorecard(o: RunOutputs, rows_clean: int) -> Scorecard:
    severity = Counter(r.severity.value.lower() for r in o.records)
    return Scorecard(
        run_id=o.run_id,
        status=o.status,
        rows_in=sum(t.rows for t in o.ingest.tables),
        rows_mapped=mapped_rows(o.tables),
        rows_clean=rows_clean,
        exceptions_by_severity=SeverityCounts(
            blocker=severity["blocker"],
            error=severity["error"],
            warning=severity["warning"],
            info=severity["info"],
        ),
        exceptions_by_rule=dict(sorted(Counter(r.rule_id for r in o.records).items())),
        tie_out=tuple(
            LegSummary.model_validate(leg.model_dump(exclude={"variances"})) for leg in o.tie.legs
        ),
        rts_gaps=sum(c.coverage == RtsCellState.USED_WITHOUT_RTS for c in o.coverage.cells),
        detection=o.detection,
    )


def _json(model: StrictModel, path: Path) -> None:
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def write_run(o: RunOutputs, run_dir: Path) -> None:
    rows_clean = 0
    if o.status != RunStatus.FAILED:
        count = len(o.records)
        clean = clean_tables(o.tables, o.records)
        if len(o.records) != count:
            raise ValueError(
                "Collect MAP-004 errors before calculating run status or writing files"
            )
        write_clean(clean, run_dir)
        rows_clean = clean_row_count(clean)
    _json(manifest(o), run_dir / "manifest.json")
    _json(scorecard(o, rows_clean), run_dir / "scorecard.json")
    _json(o.coverage, run_dir / "rts_coverage.json")
    write_tieout(o.tie, run_dir)
    lines = "".join(r.model_dump_json() + "\n" for r in o.records)
    (run_dir / "exceptions.jsonl").write_text(lines, encoding="utf-8")
    (run_dir / "unresolved_evidence.jsonl").write_text(
        serialize_unresolved_evidence(o.unresolved, o.run_id), encoding="utf-8"
    )
    if o.statement_totals is not None:
        (run_dir / "statement_totals.json").write_text(
            o.statement_totals.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
