"""One bad Jev reply leaves its header or value for a person; the rest of the run is intact."""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from agency_schema.outputs import Manifest, RunStatus
from agency_schema.run_dir import check_run_dir
from intake.run import jev as run_jev
from intake.run.pipeline import RunOptions, run

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
AS_OF = datetime.fromisoformat("2026-10-01T09:00:00+00:00")


def test_bad_replies_go_to_a_person_and_the_run_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cassettes = tmp_path / "mapping"
    shutil.copytree(run_jev.MAPPING_CASSETTES, cassettes)
    edited = 0
    for path in cassettes.glob("*.json"):
        cassette = json.loads(path.read_text(encoding="utf-8"))
        state = cassette["request"]["state"]
        if state.get("header") == "Birth Dt (mm/dd/yy)" or state.get("value") == "chk w/ carrier":
            answer = next(iter(cassette["response"]["answers"].values()))
            answer["choice"] = "made.up_field"  # not among the offered options
            path.write_text(json.dumps(cassette), encoding="utf-8")
            edited += 1
    assert edited == 2  # one header and one enum recording, or the test checks nothing
    monkeypatch.setattr(run_jev, "MAPPING_CASSETTES", cassettes)

    drop = FIXTURES / "agency-a" / "drop"
    result = run(RunOptions(drop=drop, out=tmp_path / "bad-reply", as_of=AS_OF))
    check_run_dir(result.run_dir)
    assert result.status == RunStatus.PASSED_WITH_WARNINGS
    birth = [r for r in result.records if "Birth Dt" in r.message]
    assert any(r.rule_id == "MAP-002" and "invalid model answer" in r.message for r in birth)
    assert any(r.rule_id == "MAP-001" for r in birth)
    # The other Jev header still mapped, and the run kept its rows and tables.
    assert not any(r.rule_id == "MAP-001" and '"Paid"' in r.message for r in result.records)
    assert result.tables["policies"].height > 0 and result.tables["commission_lines"].height > 0
    statuses = set(result.tables["policies"]["status"].drop_nulls().to_list())
    assert "chk w/ carrier" in statuses  # kept as written, not the rejected pick
    manifest = Manifest.model_validate_json((result.run_dir / "manifest.json").read_text())
    assert manifest.jev.calls > 0 and manifest.budget_tripped is False
    # Every mapping question had a recording; only triage of the new MAP-002 went unrecorded.
    assert all(run_jev.cassette_dir_for(r) != cassettes for r in result.client.misses.values())
