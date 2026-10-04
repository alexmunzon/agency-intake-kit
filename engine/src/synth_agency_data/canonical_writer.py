"""Write a world as canonical CSVs (one per table) plus ground_truth.json.

The clean world goes to canonical/. The defected world goes to canonical-defected/, and each
defect's row_ref is set to its row in that CSV (row 1 is the header). When a key appears
twice (a duplicate), row_ref points at the later copy.

Columns follow the agency_schema model field order, without lineage (readers add lineage).
Dates are ISO, money has two decimals, list fields are joined with "|", None is blank.
Output is byte-identical for the same world, so fixtures do not churn.
"""

import csv
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from agency_schema.models import TABLE_MODELS
from synth_agency_data.world import World

LIST_SEPARATOR = "|"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple):
        return LIST_SEPARATOR.join(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _row_ref(world: World, d: dict[str, Any]) -> int:
    rows = world.tables[d["source"]]
    key = d["record_key"]
    hits = [i for i, r in enumerate(rows) if all(r[k] == v for k, v in key.items())]
    if not hits:
        raise ValueError(f"defect {d['defect_type']} points at a missing record {key}")
    return hits[-1] + 2


def write_world(
    world: World,
    out_dir: Path,
    defects: Sequence[dict[str, Any]] = (),
    folder: str = "canonical",
) -> None:
    canonical = out_dir / folder
    canonical.mkdir(parents=True, exist_ok=True)
    for table, model in TABLE_MODELS.items():
        columns = [name for name in model.model_fields if name != "lineage"]
        with (canonical / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows([_cell(row[c]) for c in columns] for row in world.tables[table])
    # Each defect: {source, record_key, row_ref, defect_type, expected_rule_ids, scored,
    # injected_values}. The clean world has none.
    truth = {"seed": world.seed, "defects": [{**d, "row_ref": _row_ref(world, d)} for d in defects]}
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")


def load_ground_truth(path: Path) -> dict[str, Any]:
    truth: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return truth
