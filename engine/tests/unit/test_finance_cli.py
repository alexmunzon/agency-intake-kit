import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intake import finance_cli
from intake.finance_cli import app

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def test_local_cli_roundtrip_and_immutable_export(tmp_path):
    runner = CliRunner()
    store = tmp_path / "ledger.sqlite"
    output = tmp_path / "ledger.json"
    assert (
        runner.invoke(
            app, ["init", str(store), str(FIXTURES / "finance-review/mapping.json")]
        ).exit_code
        == 0
    )
    args = ["append", str(store), "operation", str(FIXTURES / "finance-durable/batch.json")]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    assert runner.invoke(app, args).output == first.output
    assert runner.invoke(app, ["export", str(store), str(output)]).exit_code == 0
    assert json.loads(output.read_text()) == json.loads(first.output)
    before = output.read_bytes()
    assert runner.invoke(app, ["export", str(store), str(output)]).exit_code != 0
    assert output.read_bytes() == before


def test_refusal_does_not_echo_input(tmp_path):
    source = tmp_path / "malformed.json"
    source.write_text('{"SENSITIVE_MARKER": "invalid"}')
    result = CliRunner().invoke(app, ["init", str(tmp_path / "store"), str(source)])
    assert result.exit_code == 1
    assert "SENSITIVE_MARKER" not in result.output
    assert "Finance operation refused" in result.output
    assert not (tmp_path / "store").exists()


@pytest.mark.parametrize("command", ["import-statement", "export"])
def test_output_write_failure_leaves_no_partial_file_and_can_retry(tmp_path, monkeypatch, command):
    runner = CliRunner()
    output = tmp_path / "result.json"
    if command == "import-statement":
        args = [
            command,
            str(FIXTURES / "finance-durable/statement.csv"),
            str(FIXTURES / "finance-durable/adapter.json"),
            str(output),
        ]
    else:
        store = tmp_path / "ledger.sqlite"
        assert (
            runner.invoke(
                app, ["init", str(store), str(FIXTURES / "finance-review/mapping.json")]
            ).exit_code
            == 0
        )
        args = [command, str(store), str(output)]

    original_fdopen = os.fdopen

    class PartialWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:8])
            raise OSError("synthetic partial write")

    monkeypatch.setattr(
        finance_cli.os, "fdopen", lambda fd, mode: PartialWriter(original_fdopen(fd, mode))
    )
    refused = runner.invoke(app, args)
    assert refused.exit_code == 1
    assert not output.exists()
    assert list(tmp_path.glob(".finance-*")) == []

    monkeypatch.setattr(finance_cli.os, "fdopen", original_fdopen)
    assert runner.invoke(app, args).exit_code == 0
    assert json.loads(output.read_text())


def test_concurrent_exports_publish_once_without_clobber(tmp_path):
    runner = CliRunner()
    store = tmp_path / "ledger.sqlite"
    output = tmp_path / "ledger.json"
    assert (
        runner.invoke(
            app, ["init", str(store), str(FIXTURES / "finance-review/mapping.json")]
        ).exit_code
        == 0
    )
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    command = [sys.executable, "-m", "intake.finance_cli", "export", str(store), str(output)]

    def run_export():
        return subprocess.run(command, env=environment, capture_output=True, text=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_export(), range(2)))
    assert sorted(result.returncode for result in results) == [0, 1]
    assert json.loads(output.read_text())["artifact_type"] == "neutral_finance_ledger"
    assert list(tmp_path.glob(".finance-*")) == []
