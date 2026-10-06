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
from synth_agency_data.injectors.base import AGGREGATE_DEFECTS
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


RowIndexes = dict[tuple[str, tuple[str, ...]], dict[tuple[Any, ...], int]]


def _row_ref(world: World, d: dict[str, Any], indexes: RowIndexes | None = None) -> int | None:
    if d["source"] not in world.tables or d["defect_type"] in AGGREGATE_DEFECTS:
        return None  # a file-level defect or a total (TIE-005) has no canonical row
    rows = world.tables[d["source"]]
    key = d["record_key"]
    indexes = {} if indexes is None else indexes
    fields = tuple(sorted(key))
    shape = (d["source"], fields)
    if shape not in indexes:
        indexes[shape] = {
            tuple(row[field] for field in fields): i + 2 for i, row in enumerate(rows)
        }
    try:
        return indexes[shape][tuple(key[field] for field in fields)]
    except KeyError as error:
        raise ValueError(f"defect {d['defect_type']} points at a missing record {key}") from error


def write_world(
    world: World,
    out_dir: Path,
    defects: Sequence[dict[str, Any]] = (),
    folder: str = "canonical",
) -> None:
    write_tables(world, out_dir / folder)
    write_ground_truth(world, out_dir, defects)


def write_tables(world: World, canonical: Path) -> None:
    canonical.mkdir(parents=True, exist_ok=True)
    for table, model in TABLE_MODELS.items():
        columns = [name for name in model.model_fields if name != "lineage"]
        with (canonical / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows([_cell(row[c]) for c in columns] for row in world.tables[table])


def write_ground_truth(world: World, out_dir: Path, defects: Sequence[dict[str, Any]]) -> None:
    # Each defect: {source, record_key, row_ref, defect_type, expected_rule_ids, scored,
    # injected_values}, plus source_file, sheet, source_row once PR 3b writes the drop.
    indexes: RowIndexes = {}
    truth = {
        "seed": world.seed,
        "defects": [{**d, "row_ref": _row_ref(world, d, indexes)} for d in defects],
    }
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")


def load_ground_truth(path: Path) -> dict[str, Any]:
    truth: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return truth
