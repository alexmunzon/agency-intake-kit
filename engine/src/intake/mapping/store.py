"""The mapping store: mapping/<source>.yaml, one file per source, kept beside drop/.

A file records how each header was mapped. On the next run its decisions win over the
synonym table, so a mapping a person confirmed or corrected is reused. Writing what was
read gives back the same bytes, so an unchanged mapping never churns in git.

`intake mapping apply` adds a per-source format_fingerprint and, on manual entries, the
reviewer and the suggestion they acted on. These are optional and left out of the file when
empty, so older files load and write back unchanged.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import Field, model_validator

from agency_schema.lineage import NonEmpty, OptionalText, StrictModel
from agency_schema.mapping_review import FieldRef, Fingerprint, Origin

# synonym: matched data/synonyms.yaml. jev: chosen by Jev (PR 7). manual: set by a person,
# and a manual entry with no field means "ignore this column". unmapped: nothing matched
# yet, so the next run tries again.
Method = Literal["synonym", "jev", "manual", "unmapped"]


class MappingEntry(StrictModel):
    header: NonEmpty  # exactly as it appears in the file
    table: OptionalText
    field: OptionalText
    method: Method
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None
    decided_at: NonEmpty  # ISO 8601 timestamp
    # Set by `intake mapping apply` on manual entries only. The reviewer is a name as typed,
    # not an authenticated identity.
    reviewer: OptionalText = None
    suggested_field: FieldRef | None = None
    suggested_origin: Origin | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.table is None) != (self.field is None):
            raise ValueError(f"{self.header!r}: give both table and field, or neither")
        reviewed = (self.reviewer, self.suggested_field, self.suggested_origin)
        if any(v is not None for v in reviewed) and self.method != "manual":
            raise ValueError(f"{self.header!r}: review details belong on manual entries only")
        if self.field is None and self.method not in ("manual", "unmapped"):
            raise ValueError(f"{self.header!r}: method {self.method} needs a field")
        if self.field is not None and self.method == "unmapped":
            raise ValueError(f"{self.header!r}: an unmapped entry has no field")
        return self


class SourceMapping(StrictModel):
    source: NonEmpty
    format_fingerprint: Fingerprint | None = None  # the header list the saved decisions are for
    entries: tuple[MappingEntry, ...]

    def entry(self, header: str) -> MappingEntry | None:
        return next((e for e in self.entries if e.header == header), None)


def mapping_dir_for(drop_dir: Path) -> Path:
    """mapping/ sits beside drop/, like ground_truth.json, so it outlives every run."""
    return drop_dir.parent / "mapping"


def mapping_path(mapping_dir: Path, source: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", source):
        raise ValueError("mapping source must be a safe file identifier")
    path = mapping_dir / f"{source}.yaml"
    if mapping_dir.is_symlink() or path.is_symlink():
        raise ValueError("mapping folders and files cannot be symlinks")
    return path


OPTIONAL_KEYS = ("format_fingerprint", "reviewer", "suggested_field", "suggested_origin")


def _without_empty_optional(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if not (k in OPTIONAL_KEYS and v is None)}


def dump_mapping(mapping: SourceMapping) -> str:
    data = mapping.model_dump(mode="json")
    entries = [_without_empty_optional(e) for e in data.pop("entries")]
    data = {**_without_empty_optional(data), "entries": entries}
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )


def parse_mapping(text: str) -> SourceMapping:
    return SourceMapping.model_validate(yaml.safe_load(text))


def load_mapping(mapping_dir: Path, source: str) -> SourceMapping | None:
    path = mapping_path(mapping_dir, source)
    if not path.exists():
        return None
    mapping = parse_mapping(path.read_text(encoding="utf-8"))
    if mapping.source != source:
        raise ValueError(f"{path.name} is for source {mapping.source}, not {source}")
    return mapping


def reusable(stored: SourceMapping | None, fingerprint: str) -> SourceMapping | None:
    """The saved mapping when its decisions may be reused for a file with this fingerprint.

    A file saved with no fingerprint is reused as before. A different fingerprint means the
    export format changed, so none of its decisions are reused (MAP-005 says why).
    """
    if stored is None or stored.format_fingerprint in (None, fingerprint):
        return stored
    return None


def save_mapping(mapping_dir: Path, mapping: SourceMapping) -> Path:
    """Write atomically: a crash leaves the old file or the new one, never half of either."""
    path = mapping_path(mapping_dir, mapping.source)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dump_mapping(mapping)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        temp = Path(handle.name)
        try:
            handle.write(text)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    temp.chmod(0o644)
    os.replace(temp, path)
    return path
