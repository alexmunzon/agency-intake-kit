"""The transport is strict, hash-bound, and safe to load from a local run directory."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from intake.adapters.contract import (
    CoverageFile,
    Packet,
    canonical_json,
    pin,
    read_pinned,
    safe_path,
)


@pytest.mark.parametrize("path", ["../outside", "/tmp/outside", "folder/../../outside", "a\\b"])
def test_path_escape_is_refused(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        safe_path(tmp_path, path)


def test_symlink_escape_is_refused(tmp_path: Path) -> None:
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="path"):
        safe_path(tmp_path, "escape/outside")


def test_hash_is_exact_bytes(tmp_path: Path) -> None:
    p = tmp_path / "source"
    p.write_bytes(b"first\n")
    artifact = pin(tmp_path, "source")
    assert read_pinned(tmp_path, artifact) == b"first\n"
    p.write_bytes(b"other\n")
    with pytest.raises(ValueError, match="stale"):
        read_pinned(tmp_path, artifact)


def test_contract_versions_unknown_fields_and_schema() -> None:
    p = Packet(
        agency_id="a",
        run_id="i",
        intake_run_id="i",
        data_kind="synthetic",
        artifacts=(),
        clients=(),
        policies=(),
    )
    assert Packet.model_validate_json(canonical_json(p)) == p
    for change in ({"schema_version": "2.0.0"}, {"unexpected": True}, {"data_kind": "real"}):
        with pytest.raises(ValidationError):
            Packet.model_validate(p.model_dump() | change)
    docs = Path(__file__).resolve().parents[3] / "docs/contracts"
    assert (
        json.loads((docs / "agency-packet-v1.schema.json").read_text())
        == Packet.model_json_schema()
    )
    assert (
        json.loads((docs / "coverage-v1.schema.json").read_text())
        == CoverageFile.model_json_schema()
    )
