"""Orchestration regressions: a run owns only its uniquely allocated backup."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from agency_schema.outputs import JevMode
from intake.run import pipeline


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("existing_output", [False, True])
def test_old_backup_name_can_hold_input_without_being_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nested: bool, existing_output: bool
) -> None:
    old_name = tmp_path / ".result-replaced"
    drop = old_name / "input" if nested else old_name
    drop.mkdir(parents=True)
    (drop / "manifest.json").write_text("{}")
    (drop / "evidence.csv").write_text("synthetic evidence")
    out = tmp_path / "result"
    if existing_output:
        out.mkdir()
        (out / "previous").write_text("old run")
    monkeypatch.setattr(pipeline, "_run_into", Mock(return_value=None))

    pipeline.run(pipeline.RunOptions(drop=drop, out=out, overwrite=True, jev_mode=JevMode.OFF))

    assert (drop / "evidence.csv").read_text() == "synthetic evidence"
    assert (drop / "manifest.json").read_text() == "{}"
    assert out.is_dir()
    assert not list(tmp_path.glob(".result-replaced-*"))


def test_existing_backup_symlink_and_its_target_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drop = tmp_path / "input"
    drop.mkdir()
    (drop / "manifest.json").write_text("{}")
    alias = tmp_path / ".result-replaced"
    alias.symlink_to(drop, target_is_directory=True)
    out = tmp_path / "result"
    out.mkdir()
    monkeypatch.setattr(pipeline, "_run_into", Mock(return_value=None))

    pipeline.run(pipeline.RunOptions(drop=alias, out=out, overwrite=True, jev_mode=JevMode.OFF))

    assert alias.is_symlink()
    assert (drop / "manifest.json").read_text() == "{}"
    assert out.is_dir()


def test_failed_install_keeps_previous_run_in_recoverable_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drop = tmp_path / "input"
    drop.mkdir()
    (drop / "manifest.json").write_text("{}")
    out = tmp_path / "result"
    out.mkdir()
    (out / "previous").write_text("old run")
    monkeypatch.setattr(pipeline, "_run_into", Mock(return_value=None))
    rename = Path.rename

    def fail_install(source: Path, target: Path) -> Path:
        if target == out:
            raise OSError("synthetic install failure")
        return rename(source, target)

    monkeypatch.setattr(Path, "rename", fail_install)
    with pytest.raises(OSError, match="synthetic install failure"):
        pipeline.run(pipeline.RunOptions(drop=drop, out=out, overwrite=True, jev_mode=JevMode.OFF))

    backups = list(tmp_path.glob(".result-replaced-*/run/previous"))
    assert len(backups) == 1
    assert backups[0].read_text() == "old run"
    assert (drop / "manifest.json").read_text() == "{}"
