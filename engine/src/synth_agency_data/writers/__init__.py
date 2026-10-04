"""Write the defected world as the four messy source shapes, plus drop/manifest.json.

write_drop also returns every defect with its location added: source_file, sheet (None for
a CSV), and source_row (1-based, as in the file; the header is row 1 in the CSVs and row 3
in the statements). Policy defects point at the policy's CRM row (the later copy for a
duplicated id). Client defects point at the client's first CRM row. Line defects point at
the statement row. A row cut off by truncation gets source_row None.
"""

import json
from pathlib import Path
from typing import Any

from synth_agency_data.injectors.base import Defect, defect
from synth_agency_data.world import World
from synth_agency_data.writers import commissions, crm, enrollment, roster
from synth_agency_data.writers.common import Location
from synth_agency_data.writers.notes import plant_notes

__all__ = ["write_drop"]


def _locate(d: Defect, where: dict[str, Any]) -> Location:
    key = d["record_key"]
    if d["source"] == "commission_lines":
        line: Location = where["lines"][
            f"{key['carrier']}|{key['statement_period']}|{key['line_no']}"
        ]
        return line
    table = "policies" if d["source"] == "policies" else "clients"
    row: int = where[table][next(iter(key.values()))]
    return crm.FILE, None, row


def write_drop(
    world: World,
    defects: list[Defect],
    drop: Path,
    truncate_crm: int | None = None,
    add_ssn: bool = False,
    plant_pii: bool = True,
) -> list[Defect]:
    """plant_pii=False (the clean world) writes harmless notes only."""
    drop.mkdir(parents=True, exist_ok=True)
    notes, pii = plant_notes(world, plant_pii)
    placed = _write_files(world, notes, drop, truncate_crm, add_ssn)
    located = []
    for d in defects + pii:
        file, sheet, row = _locate(d, placed)
        cut = file == crm.FILE and truncate_crm is not None and row > truncate_crm + 1
        located.append(
            {**d, "source_file": file, "sheet": sheet, "source_row": None if cut else row}
        )
    if truncate_crm is not None:
        lost = defect(
            "truncated_file",
            "crm_export",
            {"source_file": crm.FILE},
            "CMP-001",
            rows_expected=placed["crm_rows"],
            rows_received=truncate_crm,
        )
        located.append(
            {**lost, "source_file": crm.FILE, "sheet": None, "source_row": truncate_crm + 1}
        )
    if add_ssn:
        ssn = defect(
            "ssn_column",
            "agent_roster",
            {"source_file": roster.FILE, "sheet": "Agents", "column": "SSN"},
            "SSN-001",
            values=placed["ssns"],
        )
        located.append({**ssn, "source_file": roster.FILE, "sheet": "Agents", "source_row": 1})
    return located


def _write_files(
    world: World, notes: dict[str, str], drop: Path, truncate_crm: int | None, add_ssn: bool
) -> dict[str, Any]:
    """Write all four shapes and the manifest. The manifest always has the full counts."""
    placed = crm.write_crm(world, notes, drop, truncate_crm)
    line_counts, lines = commissions.write_commissions(world, drop)
    sheet_counts, ssns = roster.write_roster(world, drop, add_ssn)
    files: list[dict[str, Any]] = [
        {"source": "crm", "file_name": crm.FILE, "sheet": None, "rows": placed["rows"]},
        {
            "source": "enrollment",
            "file_name": enrollment.FILE,
            "sheet": None,
            "rows": enrollment.write_enrollment(world, drop),
        },
    ]
    for name, count in line_counts.items():
        source = "statement_" + name.removeprefix("commissions_").removesuffix(".xlsx")
        files.append(
            {"source": source, "file_name": name, "sheet": commissions.SHEET, "rows": count}
        )
    for sheet, count in sheet_counts.items():
        files.append({"source": "roster", "file_name": roster.FILE, "sheet": sheet, "rows": count})
    manifest = {"seed": world.seed, "files": files}
    (drop / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "policies": placed["policies"],
        "clients": placed["clients"],
        "crm_rows": placed["rows"],
        "lines": lines,
        "ssns": ssns,
    }
