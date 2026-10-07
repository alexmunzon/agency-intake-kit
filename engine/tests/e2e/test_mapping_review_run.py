"""mapping_review.json in real runs: valid, and each MAP-001 or MAP-002 header listed once."""

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from agency_schema.exceptions import ExceptionRecord
from agency_schema.mapping_review import MappingReview
from agency_schema.outputs import JevMode, Manifest
from intake.run import jev as run_jev
from intake.run.pipeline import RunOptions, RunResult, run

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
AS_OF = datetime.fromisoformat("2026-10-01T09:00:00+00:00")
DEMO = Path(__file__).resolve().parents[3] / "dashboard" / "public" / "demo-run"
MAP_RULES = ("MAP-001", "MAP-002")


def review_of(run_dir: Path) -> MappingReview:
    return MappingReview.model_validate_json((run_dir / "mapping_review.json").read_text())


def records_of(run_dir: Path) -> list[ExceptionRecord]:
    lines = (run_dir / "exceptions.jsonl").read_text().splitlines()
    return [ExceptionRecord.model_validate_json(line) for line in lines if line]


def assert_each_map_header_once(run_dir: Path) -> MappingReview:
    review = review_of(run_dir)
    linked = Counter(ex_id for item in review.items for ex_id in item.exception_ids)
    for record in records_of(run_dir):
        if record.rule_id in MAP_RULES:
            assert linked[record.id] == 1, f"{record.id} is not listed exactly once"
    per_header = Counter((i.source, i.header) for i in review.items)
    assert all(n == 1 for n in per_header.values())
    return review


def test_the_demo_run_has_a_valid_review_file() -> None:
    review = assert_each_map_header_once(DEMO)
    manifest = Manifest.model_validate_json((DEMO / "manifest.json").read_text())
    assert (review.run_id, review.jev_mode) == (manifest.run_id, manifest.jev.mode)
    assert manifest.jev.invalid_answers == 0
    assert all(i.origin in ("jev_replay", "none") for i in review.items)


def test_agency_a_review_matches_its_run(agency_a: RunResult) -> None:
    review = assert_each_map_header_once(agency_a.run_dir)
    assert review.items  # Jev is asked about the headers the synonyms leave open
    versions = {v for v in review.mapping_version.split(",")}
    assert all("-" in v for v in versions)


def test_a_bad_reply_run_lists_its_map_headers_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cassettes = tmp_path / "mapping"
    shutil.copytree(run_jev.MAPPING_CASSETTES, cassettes)
    for path in cassettes.glob("*.json"):
        cassette = json.loads(path.read_text(encoding="utf-8"))
        if cassette["request"]["state"].get("header") == "Birth Dt (mm/dd/yy)":
            next(iter(cassette["response"]["answers"].values()))["choice"] = "made.up_field"
            path.write_text(json.dumps(cassette), encoding="utf-8")
    monkeypatch.setattr(run_jev, "MAPPING_CASSETTES", cassettes)
    result = run(RunOptions(drop=FIXTURES / "agency-a" / "drop", out=tmp_path / "r", as_of=AS_OF))
    review = assert_each_map_header_once(result.run_dir)
    [birth] = [i for i in review.items if i.header == "Birth Dt (mm/dd/yy)"]
    assert (birth.route, birth.reason, birth.origin) == ("person", "invalid_reply", "none")
    assert {r.rule_id for r in result.records if r.id in birth.exception_ids} == set(MAP_RULES)
    manifest = Manifest.model_validate_json((result.run_dir / "manifest.json").read_text())
    assert manifest.jev.invalid_answers == 1


@pytest.mark.parametrize("mode", [JevMode.OFF, JevMode.REPLAY])
def test_two_files_under_one_source_finish_the_run(tmp_path: Path, mode: JevMode) -> None:
    drop = tmp_path / "drop"
    shutil.copytree(FIXTURES / "agency-a" / "drop", drop)
    shutil.copy(
        drop / "commissions_cardinal_mutual.xlsx", drop / "commissions_cardinal_mutual_feb.xlsx"
    )
    manifest = json.loads((drop / "manifest.json").read_text())
    [entry] = [f for f in manifest["files"] if f["file_name"] == "commissions_cardinal_mutual.xlsx"]
    manifest["files"].append({**entry, "file_name": "commissions_cardinal_mutual_feb.xlsx"})
    (drop / "manifest.json").write_text(json.dumps(manifest))
    result = run(RunOptions(drop=drop, out=tmp_path / "r", as_of=AS_OF, jev_mode=mode))
    review = review_of(result.run_dir)
    paid = [
        i for i in review.items if (i.source, i.header) == ("statement_cardinal_mutual", "Paid")
    ]
    assert sorted(i.file_name for i in paid) == [
        "commissions_cardinal_mutual.xlsx [Statement]",
        "commissions_cardinal_mutual_feb.xlsx [Statement]",
    ]
    assert len({i.item_id for i in paid}) == 2
    linked = {ex_id for item in review.items for ex_id in item.exception_ids}
    for record in records_of(result.run_dir):
        if record.rule_id in MAP_RULES:
            assert record.id in linked  # every MAP record is listed; one may cover both files
