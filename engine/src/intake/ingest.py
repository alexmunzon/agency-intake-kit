"""Read a drop folder into raw frames, using drop/manifest.json when it is there."""

import json
from dataclasses import dataclass, replace
from pathlib import Path

from agency_schema.exceptions import ExceptionRecord
from intake.config import RAW_MAPPING_VERSION
from intake.readers import RawTable
from intake.readers.csv import read_csv
from intake.readers.xlsx import read_xlsx

MANIFEST_NAME = "manifest.json"
TEXT_SUFFIXES = (".csv", ".txt", ".tsv")


@dataclass(frozen=True)
class ManifestEntry:
    source: str
    file_name: str
    sheet: str | None
    rows: int


@dataclass(frozen=True)
class IngestResult:
    tables: tuple[RawTable, ...]
    missing: tuple[ManifestEntry, ...]  # listed in the manifest but not found in the drop
    has_manifest: bool

    @property
    def exceptions(self) -> list[ExceptionRecord]:
        return [record for table in self.tables for record in table.exceptions]


def read_manifest(drop: Path) -> list[ManifestEntry] | None:
    path = drop / MANIFEST_NAME
    if path.is_symlink():
        raise ValueError("drop manifest cannot be a symlink")
    if not path.exists():
        return None
    files = json.loads(path.read_text(encoding="utf-8"))["files"]
    for f in files:
        if Path(f["file_name"]).name != f["file_name"]:
            raise ValueError(f"manifest file_name must be a bare file name: {f['file_name']!r}")
    return [
        ManifestEntry(f["source"], f["file_name"], f.get("sheet"), int(f["rows"])) for f in files
    ]


def _discover(drop: Path) -> list[ManifestEntry]:
    """Without a manifest every csv and xlsx file is a source named after its file."""
    return [
        ManifestEntry(p.stem, p.name, None, -1)
        for p in sorted(drop.iterdir())
        if p.suffix.lower() in (*TEXT_SUFFIXES, ".xlsx")
    ]


def ingest(drop: Path, *, run_id: str, mapping_version: str = RAW_MAPPING_VERSION) -> IngestResult:
    manifest = read_manifest(drop)
    entries = manifest if manifest is not None else _discover(drop)
    tables: list[RawTable] = []
    missing: list[ManifestEntry] = []
    by_file: dict[str, list[ManifestEntry]] = {}
    for entry in entries:
        by_file.setdefault(entry.file_name, []).append(entry)
    for file_name, group in by_file.items():
        path = drop / file_name
        if path.is_symlink() or not path.resolve().is_relative_to(drop.resolve()):
            raise ValueError("drop files must stay inside the drop folder")
        if not path.is_file():
            missing.extend(group)
            continue
        if path.suffix.lower() == ".xlsx":
            listed = {e.sheet: e.source for e in group if e.sheet is not None}
            read = read_xlsx(
                path,
                sheets=listed or None,
                run_id=run_id,
                mapping_version=mapping_version,
            )
            found = {t.sheet for t in read}
            missing.extend(e for e in group if e.sheet is not None and e.sheet not in found)
        else:
            read = [
                read_csv(
                    path, source=group[0].source, run_id=run_id, mapping_version=mapping_version
                )
            ]
        expected = {e.sheet: e.rows for e in group if e.rows >= 0}
        for table in read:
            rows = expected.get(table.sheet, expected.get(None))
            tables.append(replace(table, expected_rows=rows))
    return IngestResult(tuple(tables), tuple(missing), manifest is not None)
