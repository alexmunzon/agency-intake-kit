"""The mapping store: mapping/<source>.yaml, one file per source, kept beside drop/.

A file records how each header was mapped. On the next run its decisions win over the
synonym table, so a mapping a person confirmed or corrected is reused. Writing what was
read gives back the same bytes, so an unchanged mapping never churns in git.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import Field, model_validator

from agency_schema.lineage import NonEmpty, OptionalText, StrictModel

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

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.table is None) != (self.field is None):
            raise ValueError(f"{self.header!r}: give both table and field, or neither")
        if self.field is None and self.method not in ("manual", "unmapped"):
            raise ValueError(f"{self.header!r}: method {self.method} needs a field")
        if self.field is not None and self.method == "unmapped":
            raise ValueError(f"{self.header!r}: an unmapped entry has no field")
        return self


class SourceMapping(StrictModel):
    source: NonEmpty
    entries: tuple[MappingEntry, ...]

    def entry(self, header: str) -> MappingEntry | None:
        return next((e for e in self.entries if e.header == header), None)


def mapping_dir_for(drop_dir: Path) -> Path:
    """mapping/ sits beside drop/, like ground_truth.json, so it outlives every run."""
    return drop_dir.parent / "mapping"


def mapping_path(mapping_dir: Path, source: str) -> Path:
    return mapping_dir / f"{source}.yaml"


def dump_mapping(mapping: SourceMapping) -> str:
    return yaml.safe_dump(
        mapping.model_dump(mode="json"),
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


def save_mapping(mapping_dir: Path, mapping: SourceMapping) -> Path:
    path = mapping_path(mapping_dir, mapping.source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_mapping(mapping), encoding="utf-8", newline="\n")
    return path
