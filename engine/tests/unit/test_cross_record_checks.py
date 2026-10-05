"""PR 9: duplicates, references, RTS, and licenses, scored against ground_truth.json."""

from functools import cache
from pathlib import Path
from typing import Any

import pytest

from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.outputs import RtsCellState, RtsCoverage
from agency_schema.registry import catalog
from intake.checks import CrossRecordResult, run_cross_record_checks
from intake.run.canonicalize import frame_from_rows
from intake.run.pipeline import canonical_from_drop
from synth_agency_data.canonical_writer import load_ground_truth
from synth_agency_data.world import build_world
from synth_agency_data.writers import write_drop

FIXTURE = Path(__file__).parents[3] / "fixtures" / "agency-a"
DROP = FIXTURE / "drop"
RULES = {
    "DUP-001": "WARNING",
    "DUP-002": "WARNING",
    "DUP-003": "ERROR",
    "REF-001": "ERROR",
    "RTS-001": "ERROR",
    "RTS-002": "WARNING",
    "LIC-001": "ERROR",
}
Key = tuple[str, tuple[tuple[str, str], ...]]


@cache
def defected() -> tuple[dict[str, Any], CrossRecordResult]:
    tables = canonical_from_drop(DROP).tables
    return tables, run_cross_record_checks(tables)


@cache
def truth() -> list[dict[str, Any]]:
    return list(load_ground_truth(FIXTURE / "ground_truth.json")["defects"])


def record_key(tables: dict[str, Any], r: ExceptionRecord, fields: list[str]) -> Key:
    assert r.lineage is not None
    frame = tables[r.source]
    where = (r.lineage.source_file, r.lineage.sheet, r.lineage.row_number)
    hits = [
        row
        for row in frame.iter_rows(named=True)
        if (row["lineage"]["source_file"], row["lineage"]["sheet"], row["lineage"]["row_number"])
        == where
    ]
    assert len(hits) == 1, f"{where} is not exactly one row of {r.source}"
    row = hits[0]
    return r.source, tuple((f, str(row[f])) for f in fields)


def gt_key(d: dict[str, Any]) -> Key:
    return d["source"], tuple((k, str(v)) for k, v in d["record_key"].items())


def test_rules_are_registered_and_never_block() -> None:
    meta = {m.rule_id: m for m in catalog()}
    for rule_id, severity in RULES.items():
        assert meta[rule_id].severity == severity
        assert not meta[rule_id].blocks
    assert all(not r.blocks_load for r in defected()[1].records)


@pytest.mark.parametrize("rule_id", sorted(RULES))
def test_rule_fires_on_every_planted_defect(rule_id: str) -> None:
    tables, result = defected()
    planted = [d for d in truth() if rule_id in d["expected_rule_ids"]]
    assert planted, f"ground truth plants no {rule_id}"
    fields = list(planted[0]["record_key"])
    found = {record_key(tables, r, fields) for r in result.records if r.rule_id == rule_id}
    missed = [gt_key(d) for d in planted if gt_key(d) not in found]
    assert not missed, f"{rule_id} missed {missed}"


def test_dup_002_fires_only_on_labeled_clients() -> None:
    """Issue 26: the original of each copied client is labeled too, so no DUP-002 is unexpected."""
    tables, result = defected()
    labeled = {gt_key(d) for d in truth() if "DUP-002" in d["expected_rule_ids"]}
    found = {record_key(tables, r, ["client_id"]) for r in result.records if r.rule_id == "DUP-002"}
    assert found == labeled


def test_unknown_agents_are_left_to_the_npn_rules() -> None:
    tables, result = defected()
    npn_rows = {
        (d["source_file"], d["sheet"], d["source_row"])
        for d in truth()
        if {"NPN-001", "NPN-002"} & set(d["expected_rule_ids"])
    }
    hits = [
        r
        for r in result.records
        if r.lineage
        and (r.lineage.source_file, r.lineage.sheet, r.lineage.row_number) in npn_rows
        and r.source == "policies"
    ]
    assert not [r for r in hits if r.rule_id in ("RTS-001", "RTS-002", "LIC-001")]


def test_example_3_rts_gap_by_exact_id() -> None:
    _, result = defected()
    by_id = {r.id: r for r in result.records}
    gap = by_id["RTS-001:policies:crm_export:426"]
    assert (gap.rule_id, gap.severity, gap.field) == ("RTS-001", "ERROR", "writing_agent_npn")
    assert gap.value_minimized == minimize_value("1884412")
    assert gap.message == "The writing agent is not ready to sell Harborline in TX for 2026"
    assert gap.suggested_fix == "Obtain RTS or reassign writing agent"
    assert "1884412" not in gap.message
    cells = {(c.npn, c.carrier, c.state, c.plan_year): c for c in result.coverage.cells}
    cell = cells[("1884412", "Harborline", "TX", 2026)]
    assert cell.coverage == RtsCellState.USED_WITHOUT_RTS
    assert "RTS-001:policies:crm_export:426" in cell.exception_ids


def test_coverage_cells_match_ground_truth() -> None:
    tables, result = defected()
    coverage = RtsCoverage.model_validate_json(result.coverage.model_dump_json())
    by_id = {r.id: r for r in result.records}
    cells = {(c.npn, c.carrier, c.state, c.plan_year): c for c in coverage.cells}
    policies = tables["policies"]
    for d in truth():
        if d["defect_type"] != "rts_gap":
            continue
        p = policies.filter(policies["policy_id"] == d["record_key"]["policy_id"]).row(
            0, named=True
        )
        year = int(p["effective_date"][:4])  # plan year is the effective year
        cell = cells[(p["writing_agent_npn"], p["carrier"], p["state"], year)]
        assert cell.coverage == RtsCellState.USED_WITHOUT_RTS
        assert f"RTS-001:policies:crm_export:{d['source_row']}" in cell.exception_ids
    for cell in coverage.cells:
        for ex_id in cell.exception_ids:
            assert by_id[ex_id].rule_id == "RTS-001"
    writers = set(policies["writing_agent_npn"].to_list())
    idle = [c for c in coverage.cells if c.npn not in writers]
    assert all(c.coverage == RtsCellState.HELD_UNUSED for c in idle)


def test_small_world_precedence_fallback_and_idle_agent() -> None:
    rts = dict(appointed="true", certified="true", effective_date="2026-01-01", end_date="")
    rts_row = dict(npn="111", carrier="Bluepeak", state="TX", plan_year="2026")
    policy = dict(carrier="Bluepeak", line_of_business="MA", effective_date="2026-03-01")
    tables = {
        name: frame_from_rows(f"{name}.csv", rows)
        for name, rows in {
            "clients": [
                dict(
                    client_id="C-1", first_name="Ann", last_name="Lee", dob="1950-01-02", state="TX"
                ),
                dict(
                    client_id="C-2",
                    first_name="ANN",
                    last_name="Lee.",
                    dob="1950-01-02",
                    state="OK",
                ),
            ],
            "agents": [
                dict(npn="111", license_states="TX|OK"),
                dict(npn="222", license_states="TX"),
            ],
            "rts": [
                {**rts_row, "line_of_business": "MA", **rts, "end_date": "2026-01-31"},
                {**rts_row, "line_of_business": "PDP", **rts},
                {**rts_row, "npn": "222", "line_of_business": "MA", **rts},
            ],
            "policies": [
                dict(
                    policy_id="P-1", client_id="C-1", state="TX", writing_agent_npn="111", **policy
                ),
                dict(policy_id="P-2", client_id="C-2", state="", writing_agent_npn="111", **policy),
                dict(
                    policy_id="P-3", client_id="C-9", state="TX", writing_agent_npn="999", **policy
                ),
            ],
        }.items()
    }
    result = run_cross_record_checks(tables)
    got = sorted((r.rule_id, r.row_number) for r in result.records)
    assert got == [
        ("DUP-002", 2),
        ("DUP-002", 3),
        ("REF-001", 4),
        ("RTS-001", 3),  # P-2 falls back to the client's state, OK, where there is no RTS
        ("RTS-002", 2),  # the TX row exists but ended before P-1 took effect
    ]
    dup = [r for r in result.records if r.rule_id == "DUP-002"]
    assert {r.message for r in dup} == {"Possible duplicate person (group C-1)"}
    cells = {(c.npn, c.state): c.coverage for c in result.coverage.cells}
    assert cells == {
        ("111", "TX"): RtsCellState.HELD_AND_USED,
        ("111", "OK"): RtsCellState.USED_WITHOUT_RTS,
        ("222", "TX"): RtsCellState.HELD_UNUSED,
    }


def test_clean_world_is_silent(tmp_path: Path) -> None:
    write_drop(build_world(seed=42, n_clients=2000), [], tmp_path / "drop", plant_pii=False)
    result = run_cross_record_checks(canonical_from_drop(tmp_path / "drop").tables)
    assert result.records == []
    states = {c.coverage for c in result.coverage.cells}
    assert RtsCellState.USED_WITHOUT_RTS not in states
    assert RtsCellState.HELD_AND_USED in states
