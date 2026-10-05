"""intake run: every stage in order, from a drop folder to an immutable run directory.

ingest -> raw gates (SSN-001, CMP-001, CMP-002) -> header mapping (PR 5 synonyms, then PR 7 Jev)
-> canonical tables and enum values -> PII gate on notes -> row rules -> cross-record checks and
RTS coverage -> tie-out -> blocking policy, triage -> run files -> check_run_dir.

Raw gates run before any model call. A blocker at the raw gates or at mapping stops the run
there: the model stages and the tie-out do not run (every leg NOT_RUN with the reason), RTS
coverage is empty, and clean/ is not written. The run is written to a temporary folder beside
the target, checked, and renamed into place, so a run directory is never half written.
"""

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import JevMode, RtsCoverage, RunStatus
from agency_schema.run_dir import check_run_dir
from intake.checks import run_cross_record_checks
from intake.exceptions.pii import pii_gate
from intake.exceptions.policy import apply_policy, run_status
from intake.exceptions.triage import attach_rows, queue_order, triage
from intake.gates import run_raw_gates
from intake.ingest import MANIFEST_NAME, IngestResult, ingest
from intake.mapping.headers import SOURCE_TABLES, _missing_required, map_table
from intake.mapping.jev_mapping import Asker, map_with_jev
from intake.mapping.store import mapping_dir_for
from intake.readers import LINEAGE_COLUMN
from intake.report.html import render_report
from intake.rules import run_row_rules
from intake.rules.frames import client_frame, policy_frame
from intake.run.canonicalize import (
    Canonical,
    EnrollmentCheck,
    MappedSource,
    canonicalize,
    check_enrollment,
)
from intake.run.jev import RunJevClient
from intake.run.scoring import Score, load_ground_truth, score
from intake.run.write import RunOutputs, write_run
from intake.tieout import TieOutResult, run_tieout
from intake.tieout.variances import _not_run as tieout_not_run

GROUND_TRUTH = "ground_truth.json"
RAW_KEPT_FOR_RULES = ("status", "state", "line_of_business")


class RunRefused(Exception):  # noqa: N818  (a refusal to start, not a crash)
    """The run cannot start: no drop, no manifest, or the run folder exists without --overwrite."""


@dataclass
class RunOptions:
    drop: Path
    out: Path  # the run folder; its name is the run_id
    jev_mode: JevMode = JevMode.REPLAY
    as_of: datetime | None = None  # frozen clock; None means the real clock
    overwrite: bool = False
    client: RunJevClient | None = None  # record-run passes its own spending client


@dataclass
class RunResult:
    run_dir: Path
    status: RunStatus
    records: list[ExceptionRecord]
    tables: dict[str, pl.DataFrame]
    client: RunJevClient
    score: Score | None
    enrollment: EnrollmentCheck | None


def _blocked(records: list[ExceptionRecord]) -> bool:
    return any(r.severity == Severity.BLOCKER for r in records)


def _stop_reason(records: list[ExceptionRecord]) -> str:
    rules = sorted({r.rule_id for r in records if r.severity == Severity.BLOCKER})
    return f"A blocker ({', '.join(rules)}) stopped the run before the tie-out"


def map_drop(
    raw: IngestResult, mapping_dir: Path, now: datetime, asker: Asker
) -> tuple[list[MappedSource], list[ExceptionRecord]]:
    """PR 5 synonyms then PR 7 Jev for every raw table, exactly as `fill_drop` asks."""
    sources, records = [], []
    for table in raw.tables:
        result, _ = map_with_jev(table, map_table(table, mapping_dir, now), mapping_dir, now, asker)
        sources.append(MappedSource(table, result))
        records += result.exceptions
    if not any(t.source == "crm" for t in raw.tables):  # #59: no CRM means no book to load
        records += _missing_required("crm", SOURCE_TABLES["crm"], set())
    return sources, records


def canonical_from_drop(
    drop: Path,
    *,
    run_id: str = "test-run",
    mode: JevMode = JevMode.REPLAY,
    now: datetime | None = None,
) -> Canonical:
    """Read, map (synonyms, then Jev), and canonicalize a drop without writing a run (#57).

    The one real path from source files to canonical tables, for tests and tools. No raw gates
    and no PII gate run here, so never hand its notes to a model or an output.
    """
    raw = ingest(drop, run_id=run_id)
    asker = Asker(RunJevClient(mode=mode, api_key=None))
    with tempfile.TemporaryDirectory() as tmp:
        sources, _ = map_drop(raw, Path(tmp), now or datetime(2026, 10, 1, 9, tzinfo=UTC), asker)
        return canonicalize(sources, asker)


def _gate_notes(canon: Canonical, client: RunJevClient) -> list[ExceptionRecord]:
    """PII gate on every notes cell; clients keep only the gated text of their own row."""
    results = pii_gate(canon.notes, client)
    shown = {
        (n.lineage.source_file, n.lineage.sheet, n.lineage.row_number): g.text
        for n, g in zip(canon.notes, results, strict=True)
    }
    if "clients" in canon.tables:
        clients = canon.tables["clients"]
        keys = clients[LINEAGE_COLUMN].to_list()
        gated = [shown.get((k["source_file"], k["sheet"], k["row_number"])) for k in keys]
        canon.tables["clients"] = clients.with_columns(pl.Series("notes", gated, pl.String))
    return [g.record for g in results if g.record is not None]


def _row_rules(tables: Mapping[str, pl.DataFrame], as_of: datetime) -> list[ExceptionRecord]:
    if "clients" not in tables or "policies" not in tables:
        return []
    clients = client_frame(tables["clients"], as_of.date())
    agents = tables.get("agents", pl.DataFrame(schema={"npn": pl.String}))
    policies = policy_frame(tables["policies"], clients, agents, as_of.date())
    return run_row_rules(clients, policies)


def triage_frames(tables: Mapping[str, pl.DataFrame]) -> list[pl.DataFrame]:
    """The frames triage reads neighbors from. Status, state, and line of business are sent as
    the source wrote them (the rules judged those), policies carry agent_in_roster, and client
    frames come last so a CRM row's address state wins for ADR."""
    roster: list[str] = []
    if "agents" in tables:
        roster = tables["agents"]["npn"].drop_nulls().str.strip_chars().to_list()
    frames = []
    for name in ("commission_lines", "rts", "agents", "policies", "clients"):
        if name not in tables:
            continue
        frame = tables[name]
        raw = [f for f in RAW_KEPT_FOR_RULES if f"{f}_raw" in frame.columns]
        frame = frame.with_columns(pl.col(f"{f}_raw").alias(f) for f in raw).drop(
            [f"{f}_raw" for f in raw]
        )
        if name == "policies":
            known = pl.col("writing_agent_npn").str.strip_chars().is_in(roster)
            frame = frame.with_columns(
                pl.when(known)
                .then(pl.lit("true"))
                .otherwise(pl.lit("false"))
                .alias("agent_in_roster")
            )
        frames.append(frame)
    return frames


def _with_sources(records: list[ExceptionRecord], raw: IngestResult) -> list[ExceptionRecord]:
    """Every row-level record names the drop's source ("crm"), whichever stage made it."""
    by_file = {(t.source_file, t.sheet): t.source for t in raw.tables}
    out = []
    for r in records:
        source = by_file.get((r.lineage.source_file, r.lineage.sheet)) if r.lineage else None
        out.append(r.model_copy(update={"source": source}) if source else r)
    return out


def _unique(records: list[ExceptionRecord]) -> list[ExceptionRecord]:
    """One record per id. A repeat that is the same record is dropped (a duplicated CRM row
    makes MBI-003 report its client twice); a different record with the same id gets -2, -3."""
    seen: dict[str, ExceptionRecord] = {}
    out = []
    for r in records:
        if seen.get(r.id) == r:
            continue
        n, ex_id = 1, r.id
        while ex_id in seen:
            n += 1
            ex_id = f"{r.id}-{n}"
        seen[ex_id] = r
        out.append(r if ex_id == r.id else r.model_copy(update={"id": ex_id}))
    return out


def run(options: RunOptions) -> RunResult:
    drop, out = options.drop.resolve(), options.out.resolve()
    if not drop.is_dir():
        raise RunRefused(f"{drop} is not a folder. Pass the drop folder with --in.")
    if not (drop / MANIFEST_NAME).is_file():
        raise RunRefused(
            f"{drop} has no {MANIFEST_NAME}. A run needs the drop's manifest to know which "
            "file is which and how many rows each one should have."
        )
    if out.exists() and not options.overwrite:
        raise RunRefused(f"{out} already exists. Runs are immutable; pass --overwrite to redo it.")
    started = options.as_of or datetime.now(UTC)
    client = options.client or RunJevClient(mode=options.jev_mode, api_key=None)
    asker = Asker(client)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        result = _run_into(tmp, drop, out, started, options.as_of, client, asker)
        if out.exists():
            shutil.rmtree(out)
        tmp.rename(out)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return result


def _run_into(
    tmp: Path,
    drop: Path,
    out: Path,
    started: datetime,
    as_of: datetime | None,
    client: RunJevClient,
    asker: Asker,
) -> RunResult:
    raw = ingest(drop, run_id=out.name)
    records = list(raw.exceptions) + run_raw_gates(raw)  # before any model call
    tables: dict[str, pl.DataFrame] = {}
    tie: TieOutResult | None = None
    coverage = RtsCoverage(cells=())
    enrollment = None
    if not _blocked(records):
        mapping_dir = tmp / "mapping"
        stored = mapping_dir_for(drop)
        if stored.is_dir():  # decisions a person saved beside drop/ win, as in PR 5
            shutil.copytree(stored, mapping_dir)
        sources, mapped = map_drop(raw, mapping_dir, started, asker)
        records += mapped
        if not _blocked(records):
            canon = canonicalize(sources, asker)
            tables = canon.tables
            records += _gate_notes(canon, client)
            records += _row_rules(tables, started)
            checks = run_cross_record_checks(tables)
            records += checks.records
            coverage = checks.coverage
            tie = run_tieout(tables, run_id=out.name)
            records += tie.exceptions
            enrollment = check_enrollment(canon.enrollment, tables)
    if tie is None:
        tie = tieout_not_run(_stop_reason(records))
        tables = {}
    records = apply_policy(_unique(_with_sources(records, raw)))
    records = queue_order(triage(attach_rows(records, triage_frames(tables)), client))
    status = run_status(records)
    truth = drop.parent / GROUND_TRUTH
    result_score = None
    if truth.is_file() and status != RunStatus.FAILED:
        result_score = score(load_ground_truth(truth), records, tables, tie.variances.variances)
    outputs = RunOutputs(
        run_id=out.name,
        drop=drop,
        started=started,
        finished=as_of or datetime.now(UTC),
        as_of=as_of,
        ingest=raw,
        tables=tables,
        records=records,
        status=status,
        tie=tie,
        coverage=coverage,
        usage=client.usage,
        detection=result_score.summary if result_score else None,
    )
    write_run(outputs, tmp)
    check_run_dir(tmp)
    (tmp / "report.html").write_text(render_report(tmp), encoding="utf-8")
    return RunResult(out, status, records, tables, client, result_score, enrollment)
