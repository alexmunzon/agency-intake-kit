"""Row rules on the real path: the defected drop (ground truth) and the clean world as a drop."""

import json
from collections import Counter
from functools import cache
from pathlib import Path

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from intake.rules import ROW_FAMILIES, run_row_rules
from intake.rules.frames import client_frame, policy_frame
from intake.run.pipeline import canonical_from_drop
from synth_agency_data.world import AS_OF, build_world
from synth_agency_data.writers import write_drop

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "agency-a"
DROP = FIXTURE / "drop"


@cache
def defected_tables() -> dict[str, pl.DataFrame]:
    return canonical_from_drop(DROP).tables


def _run(tables: dict[str, pl.DataFrame]) -> list[ExceptionRecord]:
    clients = client_frame(tables["clients"], AS_OF)
    return run_row_rules(
        clients, policy_frame(tables["policies"], clients, tables["agents"], AS_OF)
    )


def test_every_planted_row_defect_is_detected() -> None:
    tables = defected_tables()
    fired = {
        (r.rule_id, r.lineage.source_file, r.lineage.sheet, r.lineage.row_number)
        for r in _run(tables)
    }
    truth = json.loads((FIXTURE / "ground_truth.json").read_text())["defects"]
    planted: Counter[str] = Counter()
    missed = []
    for d in truth:
        rule_ids = [r for r in d["expected_rule_ids"] if r[:3] in ROW_FAMILIES]
        if not rule_ids:
            continue
        ((key, value),) = d["record_key"].items()
        frame = tables[d["source"]]
        where = frame.filter(pl.col(key) == value)["lineage"].to_list()
        assert any(
            (w["source_file"], w["sheet"], w["row_number"])
            == (d["source_file"], d["sheet"], d["source_row"])
            for w in where
        ), "the pipeline's lineage disagrees with the ground truth's source row"
        for rule_id in rule_ids:
            planted[rule_id] += 1
            if (rule_id, d["source_file"], d["sheet"], d["source_row"]) not in fired:
                missed.append((rule_id, value))
    assert planted["STA-001"] == 52 and planted["MBI-003"] == 40
    assert missed == []


def test_clean_world_raises_nothing_above_info(tmp_path: Path) -> None:
    write_drop(build_world(seed=42, n_clients=2000), [], tmp_path / "drop", plant_pii=False)
    tables = canonical_from_drop(tmp_path / "drop").tables
    loud = [r.rule_id for r in _run(tables) if r.severity != Severity.INFO]
    assert loud == []
