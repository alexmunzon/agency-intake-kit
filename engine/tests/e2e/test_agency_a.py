"""SPEC example 1 end to end on the messy source drop (#61), plus examples 2, 3, and 4.

Every test reads the real fixtures/agency-a/drop through readers, gates, mapping (synonyms,
then Jev replay), canonicalizing, rules, checks, tie-out, triage, and the run writer.
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import JevMode, LegStatus, Manifest, RunStatus, Scorecard
from agency_schema.run_dir import check_run_dir
from intake.ingest import ingest
from intake.mapping.jev_mapping import Asker
from intake.rules.dob import dob_unparseable
from intake.run.canonicalize import canonicalize
from intake.run.clean import CLIENT_RULES
from intake.run.jev import MAPPING_CASSETTES, RunJevClient, cassette_dir_for
from intake.run.pipeline import RunOptions, RunRefused, RunResult, map_drop, run

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
AS_OF = datetime.fromisoformat("2026-10-01T09:00:00+00:00")

RECALL_MIN = 0.95
FALSE_POSITIVE_MAX = 0.005


def records(run_dir: Path) -> list[ExceptionRecord]:
    lines = (run_dir / "exceptions.jsonl").read_text().splitlines()
    return [ExceptionRecord.model_validate_json(line) for line in lines]


def unit(r: ExceptionRecord) -> tuple[str, str | None, int] | None:
    return (r.lineage.source_file, r.lineage.sheet, r.lineage.row_number) if r.lineage else None


def test_agency_a_passes_with_warnings_and_validates(agency_a: RunResult) -> None:
    check_run_dir(agency_a.run_dir)
    card = Scorecard.model_validate_json((agency_a.run_dir / "scorecard.json").read_text())
    assert card.status == RunStatus.PASSED_WITH_WARNINGS
    assert card.exceptions_by_severity.blocker == 0
    assert all(leg.status == LegStatus.RAN for leg in card.tie_out)
    for table in ("clients", "policies", "agents", "rts", "commission_lines", "households"):
        assert (agency_a.run_dir / "clean" / f"{table}.csv").is_file()
        assert (agency_a.run_dir / "clean" / f"{table}.parquet").is_file()


def test_example_1_accuracy_gates(agency_a: RunResult) -> None:
    """Recall at least 0.95 per scored defect type; false positives on clean rows at most 0.5%."""
    assert agency_a.score is not None
    low = {name: r for name, r in agency_a.score.recall().items() if r < RECALL_MIN}
    assert low == {}, f"recall under {RECALL_MIN}: {low}; missed {agency_a.score.missed}"
    assert agency_a.score.clean_rows > 7000
    fp = agency_a.score.summary.false_positive_rate
    assert fp <= FALSE_POSITIVE_MAX, agency_a.score.false_positives_by_rule
    card = Scorecard.model_validate_json((agency_a.run_dir / "scorecard.json").read_text())
    assert card.detection == agency_a.score.summary


def test_unscored_identity_defects_are_reported_not_gated(agency_a: RunResult) -> None:
    assert agency_a.score is not None
    unscored = {c.defect_class for c in agency_a.score.summary.classes if not c.scored}
    assert {"name_typo", "nickname", "near_duplicate_client"} <= unscored


def test_example_2_birth_dt_maps_by_jev_and_parses(agency_a: RunResult) -> None:
    crm = (agency_a.run_dir / "mapping" / "crm.yaml").read_text()
    assert "header: Mbr DOB\n  table: clients\n  field: dob\n  method: synonym" in crm
    entries = {e["header"]: e for e in _yaml(agency_a.run_dir / "mapping" / "enrollment.yaml")}
    birth = entries["Birth Dt (mm/dd/yy)"]
    assert (birth["table"], birth["field"], birth["method"]) == ("clients", "dob", "jev")
    assert birth["confidence"] >= 0.85
    # #62: the enrollment export is read, mapped, canonicalized, and cross-checked.
    check = agency_a.enrollment
    assert check is not None
    assert check.compared >= 1800 and check.unreadable == 0
    assert check.agree == check.compared and check.disagree == ()


def test_example_2_zero_dob_001_on_the_enrollment_rows_with_a_negative_control(
    tmp_path: Path,
) -> None:
    """DOB-001 runs on the 1,847 enrollment birth dates and finds nothing; garbled ones fire."""
    raw = ingest(FIXTURES / "agency-a" / "drop", run_id="dob-check")
    asker = Asker(RunJevClient(mode=JevMode.REPLAY, api_key=None))
    sources, _ = map_drop(raw, tmp_path, AS_OF, asker)
    enrollment = canonicalize(sources, asker).enrollment
    assert enrollment is not None and enrollment.height == 1847
    frame = enrollment.select("dob", "lineage").with_columns(pl.lit("C-x").alias("client_id"))
    assert frame["dob"].drop_nulls().len() >= 1830  # the rule runs on every non-blank date
    assert dob_unparseable(frame) == []
    broken = frame.head(3).with_columns(pl.lit("31/31/58").alias("dob"))
    assert len(dob_unparseable(broken)) == 3


def _yaml(path: Path) -> list[dict[str, object]]:
    import yaml

    entries: list[dict[str, object]] = yaml.safe_load(path.read_text())["entries"]
    return entries


def _policy_rows(result: RunResult) -> dict[tuple[str, str | None, int], str]:
    policies = result.tables["policies"]
    return {
        (lin["source_file"], lin["sheet"], lin["row_number"]): pid
        for pid, lin in policies.select("policy_id", "lineage").iter_rows()
    }


def test_example_3_rts_gap_is_an_error_excluded_from_clean(agency_a: RunResult) -> None:
    by_unit = _policy_rows(agency_a)
    gap = next(
        r
        for r in records(agency_a.run_dir)
        if r.rule_id == "RTS-001" and by_unit[unit(r)] == "P-00417"
    )
    assert gap.severity == Severity.ERROR
    assert gap.suggested_fix == "Obtain RTS or reassign writing agent"
    clean = agency_a.run_dir / "clean"
    policies = pl.read_csv(clean / "policies.csv", infer_schema=False)["policy_id"].to_list()
    assert "P-00417" not in policies
    clients = pl.read_csv(clean / "clients.csv", infer_schema=False)["client_id"].to_list()
    assert "C-00452" in clients  # the policy is excluded, not its client
    cells = json.loads((agency_a.run_dir / "rts_coverage.json").read_text())["cells"]
    cell = next(
        c
        for c in cells
        if (c["npn"], c["carrier"], c["state"], c["plan_year"])
        == ("1884412", "Harborline", "TX", 2026)
    )
    assert cell["coverage"] == "USED_WITHOUT_RTS" and gap.id in cell["exception_ids"]


def test_example_4_orphan_payment(agency_a: RunResult) -> None:
    leg_b = json.loads((agency_a.run_dir / "tie_out" / "leg_statement_vs_book.json").read_text())
    hit = next(
        v
        for v in leg_b["variances"]
        if (v["carrier"], v["statement_period"], v["line_no"]) == ("Harborline", "2026-08", 212)
    )
    assert (hit["rule_id"], hit["carrier_member_id"], hit["paid"]) == (
        "TIE-002",
        "HL-998213",
        "61.05",
    )
    record = next(r for r in records(agency_a.run_dir) if r.id == hit["exception_id"])
    assert record.source == "statement_harborline" and record.lineage is not None
    assert (record.lineage.source_file, record.lineage.sheet) == (
        "commissions_harborline.xlsx",
        "Statement",
    )
    totals = json.loads((agency_a.run_dir / "tie_out" / "totals_by_carrier.json").read_text())
    harborline = next(r for r in totals["rows"] if r["key"] == "Harborline")
    assert Decimal(harborline["unexplained_revenue"]) >= Decimal("61.05")


def test_clean_keeps_one_copy_and_drops_exactly_the_error_rows(agency_a: RunResult) -> None:
    """#63: expected policy rows computed independently from the exceptions."""
    found = records(agency_a.run_dir)
    errors = [r for r in found if r.severity == Severity.ERROR and r.lineage]
    client_out = {unit(r) for r in errors if r.rule_id in CLIENT_RULES}
    policy_out = {unit(r) for r in errors if r.rule_id not in CLIENT_RULES}
    clients = agency_a.tables["clients"]
    kept_clients = {
        cid
        for cid, lin in clients.select("client_id", "lineage").iter_rows()
        if (lin["source_file"], lin["sheet"], lin["row_number"]) not in client_out
    }
    expected: dict[str, int] = {}
    for pid, cid, lin in (
        agency_a.tables["policies"].select("policy_id", "client_id", "lineage").iter_rows()
    ):
        where = (lin["source_file"], lin["sheet"], lin["row_number"])
        if where not in policy_out and cid in kept_clients:
            expected.setdefault(pid, lin["row_number"])  # the first copy of a duplicate
    clean = pl.read_csv(agency_a.run_dir / "clean" / "policies.csv", infer_schema=False)
    got = dict(
        zip(clean["policy_id"].to_list(), map(int, clean["lineage_row_number"]), strict=True)
    )
    assert got == expected
    assert clean["policy_id"].n_unique() == clean.height
    dropped = set(_policy_rows(agency_a).values()) - set(got)
    assert "P-00417" in dropped and len(dropped) < 300


def test_clean_parquet_keeps_money_exact(agency_a: RunResult) -> None:
    lines = pl.read_parquet(agency_a.run_dir / "clean" / "commission_lines.parquet")
    policies = pl.read_parquet(agency_a.run_dir / "clean" / "policies.parquet")
    assert lines.schema["amount"] == pl.Decimal(12, 2)
    assert policies.schema["monthly_premium"] == pl.Decimal(12, 2)
    assert policies.schema["effective_date"] == pl.Date


def test_manifest_records_inputs_clock_and_jev(agency_a: RunResult) -> None:
    m = Manifest.model_validate_json((agency_a.run_dir / "manifest.json").read_text())
    assert m.as_of == AS_OF and m.started_at == AS_OF and m.budget_tripped is False
    assert m.jev.mode == "replay" and m.jev.calls == 7
    drop = FIXTURES / "agency-a" / "drop"
    for f in m.inputs:
        assert f.sha256 == hashlib.sha256((drop / f.file_name).read_bytes()).hexdigest()
    assert {f.source for f in m.inputs} >= {"crm", "enrollment", "roster", "statement_harborline"}


def test_replay_answers_every_mapping_question(agency_a: RunResult) -> None:
    """Mapping cassettes are recorded; only triage and PII may lack a recording (PR 12)."""
    dirs = {cassette_dir_for(request) for request in agency_a.client.misses.values()}
    assert MAPPING_CASSETTES not in dirs
    triaged = [r for r in agency_a.records if r.severity in (Severity.ERROR, Severity.WARNING)]
    assert {r.lane.value for r in triaged} <= {
        "UNREVIEWED",
        "REVIEW",
        "SUGGESTED_FIX",
        "BUSINESS_EVENT",
    }


def test_frozen_clock_makes_two_runs_byte_identical(
    agency_a: RunResult, agency_a_again: RunResult
) -> None:
    first = sorted(
        p.relative_to(agency_a.run_dir) for p in agency_a.run_dir.rglob("*") if p.is_file()
    )
    second = sorted(
        p.relative_to(agency_a_again.run_dir)
        for p in agency_a_again.run_dir.rglob("*")
        if p.is_file()
    )
    assert first == second and len(first) > 20
    for name in first:
        assert (agency_a.run_dir / name).read_bytes() == (
            agency_a_again.run_dir / name
        ).read_bytes(), name


def test_report_renders_and_names_the_status(agency_a: RunResult) -> None:
    report = (agency_a.run_dir / "report.html").read_text()
    assert "PASSED_WITH_WARNINGS" in report and "Can this agency go live?" in report
    assert "<script" not in report and "http" not in report.replace("http-equiv", "")
    assert "—" not in report


def test_an_existing_run_is_refused_without_overwrite(agency_a: RunResult) -> None:
    with pytest.raises(RunRefused, match="immutable"):
        run(RunOptions(drop=FIXTURES / "agency-a" / "drop", out=agency_a.run_dir))
