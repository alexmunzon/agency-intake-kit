import json
from pathlib import Path

from typer.testing import CliRunner

from agency_schema.outputs import RUN_FILE_MODELS
from agency_schema.typescript import render_typescript
from intake.cli import app

runner = CliRunner()
TYPES_TS = Path(__file__).parents[3] / "dashboard" / "lib" / "types.ts"


def test_schema_json_describes_files_as_written() -> None:
    result = runner.invoke(app, ["schema", "--json"])
    assert result.exit_code == 0, result.output
    defs = json.loads(result.output)["$defs"]
    assert all(model.__name__ in defs for model in RUN_FILE_MODELS.values())
    assert defs["Variance"]["properties"]["paid"]["anyOf"][0]["type"] == "string"  # money is text


def test_schema_ts_writes_the_generated_file(tmp_path: Path) -> None:
    out = tmp_path / "types.ts"
    result = runner.invoke(app, ["schema", "--ts", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text() == render_typescript()


def test_generated_types_are_stable_and_committed() -> None:
    assert TYPES_TS.read_text() == render_typescript(), (
        "run: cd engine && uv run intake schema --ts"
    )


def test_typescript_shapes() -> None:
    ts = render_typescript()
    assert 'export type RunStatus = "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED";' in ts
    assert "  paid: string | null;" in ts
    assert "  variances: Variance[];" in ts
    assert "export interface ExceptionRecord {" in ts
    assert '  rule_id: "TIE-001" | "TIE-002" | "TIE-003" | "TIE-004" | "TIE-005";' in ts


def test_schema_refuses_both_flags() -> None:
    assert runner.invoke(app, ["schema", "--json", "--ts"]).exit_code != 0
