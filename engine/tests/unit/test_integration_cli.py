"""Integration exports use real runs and publish complete, immutable packets."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intake.cli import app
from intake.integration_cli import _write_new

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/integration-v1"
RUNNER = CliRunner()


def test_finance_local_registered_and_roundtrip(tmp_path: Path) -> None:
    result = RUNNER.invoke(app, ["finance-local", "--help"])
    assert result.exit_code == 0
    assert "append" in result.output and "export" in result.output
    store = tmp_path / "finance.sqlite"
    fixtures = FIXTURE.parent
    assert (
        RUNNER.invoke(
            app,
            [
                "finance-local",
                "init",
                str(store),
                str(fixtures / "finance-review/mapping.json"),
            ],
        ).exit_code
        == 0
    )
    result = RUNNER.invoke(
        app,
        [
            "finance-local",
            "append",
            str(store),
            "cli-operation",
            str(fixtures / "finance-durable/batch.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    out = tmp_path / "ledger.json"
    assert RUNNER.invoke(app, ["finance-local", "export", str(store), str(out)]).exit_code == 0
    assert json.loads(out.read_text()) == json.loads(result.output)


def test_readiness_registered_and_rejects_invalid_package(tmp_path: Path) -> None:
    result = RUNNER.invoke(app, ["readiness", "--help"])
    assert result.exit_code == 0
    assert "check" in result.output and "export" in result.output
    source = tmp_path / "invalid.json"
    source.write_text("invalid secret-value")
    result = RUNNER.invoke(app, ["readiness", "check", str(source)])
    assert result.exit_code == 2
    assert "secret-value" not in result.output


def export(out: Path, *extra: str):
    return RUNNER.invoke(
        app,
        [
            "integration",
            "export",
            "--run",
            str(FIXTURE / "intake-run"),
            "--agency-id",
            "synthetic-agency-a",
            "--run-id",
            "intake-synthetic-v1",
            "--data-kind",
            "synthetic",
            "--out",
            str(out),
            *extra,
        ],
    )


def test_export_deterministic_and_retry_does_not_overwrite(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    result = export(a)
    assert result.exit_code == 0, result.output
    assert export(b).exit_code == 0
    assert a.read_bytes() == b.read_bytes()
    original = a.read_bytes()
    assert export(a).exit_code == 2
    assert a.read_bytes() == original
    assert b'"clients":[' in original
    assert b'"notes"' not in original


@pytest.mark.parametrize(
    "extra",
    [
        ("--run-id", "wrong"),
        ("--agency-id", " "),
        ("--data-kind", "public"),
    ],
)
def test_explicit_metadata_refused(tmp_path: Path, extra: tuple[str, ...]) -> None:
    out = tmp_path / "packet.json"
    assert export(out, *extra).exit_code == 2
    assert not out.exists()


def test_malformed_run_never_publishes(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{bad secret-value")
    out = tmp_path / "out.json"
    result = export(out, "--run", str(tmp_path))
    assert result.exit_code == 2
    assert "secret-value" not in result.output
    assert not out.exists()


def test_atomic_race_preserves_winner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out.json"
    link = os.link

    def competing_link(source: str, target: Path) -> None:
        target.write_text("successful concurrent output")
        link(source, target)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(FileExistsError):
        _write_new(out, "loser")
    assert out.read_text() == "successful concurrent output"
    assert list(tmp_path.iterdir()) == [out]


def test_failed_publish_cleans_staging_and_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out.json"
    with monkeypatch.context() as patch:

        def fail(*args: object) -> None:
            raise OSError("disk failure")

        patch.setattr(os, "link", fail)
        with pytest.raises(OSError):
            _write_new(out, "complete\n")
    assert not list(tmp_path.iterdir())
    _write_new(out, "complete\n")
    assert out.read_text() == "complete\n"
