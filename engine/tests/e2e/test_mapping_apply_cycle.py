"""The whole review loop on a real drop: run, decide, apply, run again, change the export.

1. A run lists "Birth Dt (mm/dd/yy)" in mapping_review.json with Jev's replayed proposal.
2. A decisions file built the way the dashboard builds it approves that proposal.
3. `intake mapping apply` saves it as a manual entry beside drop/, with the file's fingerprint.
4. The next run reuses the saved decision: no review item for that header, and no MAP-005.
5. After the export gains a column, the saved decisions are not reused: MAP-005 names the
   added header and the Birth Dt item comes back for review.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from typer.testing import CliRunner

from agency_schema.mapping_review import DECISIONS_NOTE, MappingReview
from intake.cli import app
from intake.mapping.fingerprint import format_fingerprint
from intake.run.pipeline import RunOptions, run

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
AS_OF = datetime.fromisoformat("2026-10-01T09:00:00+00:00")

HEADER = "Birth Dt (mm/dd/yy)"
ENROLLMENT = "enrollment_export.csv"
ADDED = "Extra Ref"


def run_drop(drop: Path, out: Path) -> Path:
    return run(RunOptions(drop=drop, out=out, as_of=AS_OF)).run_dir


def _review(run_dir: Path) -> MappingReview:
    return MappingReview.model_validate_json((run_dir / "mapping_review.json").read_text())


def _items(run_dir: Path, source: str, header: str) -> list[object]:
    return [i for i in _review(run_dir).items if (i.source, i.header) == (source, header)]


def _rule_ids(run_dir: Path) -> list[str]:
    lines = (run_dir / "exceptions.jsonl").read_text().splitlines()
    return [json.loads(line)["rule_id"] for line in lines if line]


def _add_column(csv: Path) -> None:
    lines = csv.read_text(encoding="utf-8").splitlines()
    out = [f"{lines[0]};{ADDED}"] + [f"{line};R-{n}" for n, line in enumerate(lines[1:], 1)]
    csv.write_text("\n".join(out) + "\n", encoding="utf-8")


def test_run_decide_apply_rerun_then_a_changed_export(tmp_path: Path) -> None:
    drop = tmp_path / "agency" / "drop"
    shutil.copytree(FIXTURES / "agency-a" / "drop", drop)

    first = run_drop(drop, tmp_path / "first")
    [item] = [i for i in _review(first).items if i.header == HEADER]
    assert (item.source, item.proposed_field, item.origin) == (
        "enrollment",
        "clients.dob",
        "jev_replay",
    )
    assert "MAP-005" not in _rule_ids(first)

    review = _review(first)
    decisions = {
        "run_id": review.run_id,
        "mapping_version": review.mapping_version,
        "reviewer": "Test Reviewer",
        "decided_at": "2026-10-02T10:00:00+00:00",
        "note": DECISIONS_NOTE,
        "decisions": [
            {
                "item_id": item.item_id,
                "source": item.source,
                "header": item.header,
                "format_fingerprint": item.format_fingerprint,
                "action": "approve",
                "field": item.proposed_field,
            }
        ],
    }
    decisions_file = tmp_path / "decisions.json"
    decisions_file.write_text(json.dumps(decisions), encoding="utf-8")
    applied = CliRunner().invoke(
        app, ["mapping", "apply", str(decisions_file), "--run", str(first), "--in", str(drop)]
    )
    assert applied.exit_code == 0, applied.output
    assert "1 approved, 0 corrected, 0 ignored" in applied.output

    saved_path = drop.parent / "mapping" / "enrollment.yaml"
    saved = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    headers = (drop / ENROLLMENT).read_text(encoding="utf-8").splitlines()[0].split(";")
    assert saved["format_fingerprint"] == format_fingerprint(headers) == item.format_fingerprint
    [entry] = [e for e in saved["entries"] if e["header"] == HEADER]
    assert (entry["table"], entry["field"], entry["method"]) == ("clients", "dob", "manual")
    assert (entry["reviewer"], entry["suggested_field"]) == ("Test Reviewer", "clients.dob")
    assert entry["suggested_origin"] == "jev_replay"
    saved_bytes = saved_path.read_bytes()

    second = run_drop(drop, tmp_path / "second")
    assert _items(second, "enrollment", HEADER) == []  # the saved decision settled it
    before = {(i.source, i.file_name, i.header) for i in _review(first).items}
    after = {(i.source, i.file_name, i.header) for i in _review(second).items}
    assert after == before - {("enrollment", ENROLLMENT, HEADER)}  # nothing else changed
    assert _rule_ids(second).count("MAP-002") <= _rule_ids(first).count("MAP-002")
    assert "MAP-005" not in _rule_ids(second)
    assert saved_path.read_bytes() == saved_bytes  # a run never rewrites the saved decisions

    _add_column(drop / ENROLLMENT)
    third = run_drop(drop, tmp_path / "third")
    assert _rule_ids(third).count("MAP-005") == 1
    [changed] = [
        json.loads(line)
        for line in (third / "exceptions.jsonl").read_text().splitlines()
        if line and json.loads(line)["rule_id"] == "MAP-005"
    ]
    assert changed["severity"] == "WARNING" and changed["source"] == "enrollment"
    assert f'Added: "{ADDED}"' in changed["message"] and "Removed: none" in changed["message"]
    assert len(_items(third, "enrollment", HEADER)) == 1  # back for review
    assert len(_items(third, "enrollment", ADDED)) == 1
    assert saved_path.read_bytes() == saved_bytes
