"""Row rules against the PR 3a defected copy (ground truth) and the PR 2 clean world."""

import json
from collections import Counter
from pathlib import Path

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from intake.rules import ROW_FAMILIES, run_row_rules
from intake.rules._canonical_io import load_canonical
from intake.rules.frames import client_frame, policy_frame
from synth_agency_data.canonical_writer import write_world
from synth_agency_data.world import AS_OF, build_world

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "agency-a"


def _run(folder: Path) -> list[ExceptionRecord]:
    tables = load_canonical(folder)
    clients = client_frame(tables["clients"], AS_OF)
    return run_row_rules(
        clients, policy_frame(tables["policies"], clients, tables["agents"], AS_OF)
    )


def test_every_planted_row_defect_is_detected() -> None:
    tables = load_canonical(FIXTURE / "canonical-defected")
    fired = {
        (r.rule_id, r.lineage.source_file, r.row_number)
        for r in _run(FIXTURE / "canonical-defected")
    }
    truth = json.loads((FIXTURE / "ground_truth.json").read_text())["defects"]
    planted: Counter[str] = Counter()
    missed = []
    for d in truth:
        rule_ids = [r for r in d["expected_rule_ids"] if r[:3] in ROW_FAMILIES]
        if not rule_ids:
            continue
        ((key, value),) = d["record_key"].items()
        row = tables[d["source"]].row(d["row_ref"] - 2, named=True)
        assert row[key] == value, "loader row numbers disagree with ground truth row_ref"
        for rule_id in rule_ids:
            planted[rule_id] += 1
            if (rule_id, f"{d['source']}.csv", d["row_ref"]) not in fired:
                missed.append((rule_id, value))
    assert planted["STA-001"] == 52 and planted["MBI-003"] == 40
    assert missed == []


def test_clean_world_raises_nothing_above_info(tmp_path: Path) -> None:
    write_world(build_world(seed=42, n_clients=2000), tmp_path, [], "canonical")
    loud = [r.rule_id for r in _run(tmp_path / "canonical") if r.severity != Severity.INFO]
    assert loud == []
