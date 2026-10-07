"""intake mapping apply: a decisions file becomes manual entries in mapping/<source>.yaml.

Every mismatch with the run's mapping_review.json is refused before anything is written.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from agency_schema.mapping_review import DECISIONS_NOTE
from intake.cli import app
from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.headers import map_headers
from intake.mapping.store import (
    MappingEntry,
    SourceMapping,
    load_mapping,
    mapping_path,
    save_mapping,
)

HEADERS = ["Client ID", "Mbr DOB", "Cust Ref", "Lead Source"]
FP = format_fingerprint(HEADERS)
ALLOWED = ["clients.client_id", "clients.dob", "clients.email", "clients.phone", "none"]
RUN_ID = "agency-r1"
VERSION = "crm-0123456789ab"


def _item_id(source: str, header: str, file_name: str = "crm.csv") -> str:
    text = f"{source}\0{file_name}\0{header}"
    return "mr-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _item(header: str, proposed: str | None) -> dict[str, Any]:
    return {
        "item_id": _item_id("crm", header),
        "source": "crm",
        "file_name": "crm.csv",
        "header": header,
        "format_fingerprint": FP,
        "samples": [],
        "samples_withheld": True,
        "allowed_fields": ALLOWED,
        "proposed_field": proposed,
        "origin": "jev_replay" if proposed else "none",
        "confidence": 0.7 if proposed else None,
        "route": "suggest" if proposed else "person",
        "reason": None if proposed else "not_recorded",
        "rows_with_value": 2,
        "exception_ids": [],
        "explanation": "No synonym matched this header.",
    }


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    drop = tmp_path / "agency" / "drop"
    drop.mkdir(parents=True)
    rows = ["C1,1950-01-02,R1,web", "C2,1951-03-04,R2,ad"]
    (drop / "crm.csv").write_text(",".join(HEADERS) + "\n" + "\n".join(rows) + "\n")
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    review = {
        "run_id": RUN_ID,
        "mapping_version": VERSION,
        "jev_mode": "replay",
        "items": [_item("Cust Ref", "clients.email"), _item("Lead Source", None)],
    }
    (run / "mapping_review.json").write_text(json.dumps(review))
    return {"drop": drop, "run": run, "mapping": tmp_path / "agency" / "mapping"}


def _decision(header: str, action: str, field: str | None) -> dict[str, Any]:
    return {
        "item_id": _item_id("crm", header),
        "source": "crm",
        "header": header,
        "format_fingerprint": FP,
        "action": action,
        "field": field,
    }


def _decisions(*decisions: dict[str, Any], **top: Any) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "mapping_version": VERSION,
        "reviewer": "Pat Reviewer",
        "decided_at": "2026-10-06T15:00:00+00:00",
        "note": DECISIONS_NOTE,
        "decisions": list(decisions),
        **top,
    }


def _apply(world: dict[str, Path], body: dict[str, Any]) -> Any:
    path = world["run"].parent / "decisions.json"
    path.write_text(json.dumps(body))
    args = ["mapping", "apply", str(path), "--run", str(world["run"]), "--in", str(world["drop"])]
    return CliRunner().invoke(app, args)


def test_apply_writes_manual_entries_and_keeps_entries_for_this_format(
    world: dict[str, Path],
) -> None:
    kept = MappingEntry(header="Client ID", table="clients", field="client_id", method="manual",
                        confidence=None, decided_at="2026-09-01T00:00:00+00:00")  # fmt: skip
    stale = MappingEntry(header="Old Col", table="clients", field="phone", method="synonym",
                         confidence=1.0, decided_at="2026-09-01T00:00:00+00:00")  # fmt: skip
    save_mapping(world["mapping"], SourceMapping(source="crm", entries=(kept, stale)))
    before = mapping_path(world["mapping"], "crm").read_bytes()
    body = _decisions(
        _decision("Cust Ref", "approve", "clients.email"),
        _decision("Lead Source", "ignore", None),
    )
    result = _apply(world, body)
    assert result.exit_code == 0, result.output
    assert "1 approved, 0 corrected, 1 ignored" in result.output
    saved = load_mapping(world["mapping"], "crm")
    assert saved is not None and saved.format_fingerprint == FP
    assert saved.entry("Client ID") == kept  # saved for this same format, so still in force
    assert saved.entry("Old Col") is None  # not in this export: never carried forward
    assert [e.header for e in saved.entries] == HEADERS
    previous = mapping_path(world["mapping"], "crm").with_name("crm.yaml.prev")
    assert previous.read_bytes() == before
    approved, ignored = saved.entry("Cust Ref"), saved.entry("Lead Source")
    assert approved is not None and ignored is not None
    assert (approved.method, approved.table, approved.field) == ("manual", "clients", "email")
    assert (approved.reviewer, approved.suggested_field) == ("Pat Reviewer", "clients.email")
    assert approved.suggested_origin == "jev_replay"
    assert approved.decided_at == "2026-10-06T15:00:00+00:00"
    assert (ignored.method, ignored.field, ignored.suggested_origin) == ("manual", None, "none")


def test_apply_correct_then_the_next_run_reuses_it(world: dict[str, Path]) -> None:
    result = _apply(world, _decisions(_decision("Cust Ref", "correct", "clients.phone")))
    assert result.exit_code == 0, result.output
    assert "0 approved, 1 corrected, 0 ignored" in result.output
    now = datetime(2026, 10, 7, tzinfo=UTC)
    mapped = map_headers("crm", None, HEADERS, world["mapping"], now)
    entry = mapped.mapping.entry("Cust Ref")
    assert entry is not None and (entry.method, entry.field) == ("manual", "phone")
    assert not any("Cust Ref" in r.message for r in mapped.exceptions)


REFUSALS = [
    ("run", lambda d: {**d, "run_id": "other-run"}, "run id"),
    ("version", lambda d: {**d, "mapping_version": "crm-ffffffffffff"}, "mapping version"),
    ("note", lambda d: {**d, "note": "approved"}, "not valid"),
    ("unknown", lambda d: _with(d, item_id="mr-000000000000"), "not in this run"),
    ("header", lambda d: _with(d, header="Cust Reference"), "header"),
    ("fingerprint", lambda d: _with(d, format_fingerprint="0" * 16), "format"),
    ("field", lambda d: _with(d, action="correct", field="clients.state"), "not an allowed"),
    ("approve", lambda d: _with(d, field="clients.dob"), "proposed"),
    ("source", lambda d: _with(d, source="enrollment"), "source"),
]


def _with(body: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**body, "decisions": [{**body["decisions"][0], **changes}]}


@pytest.mark.parametrize(("name", "change", "words"), REFUSALS, ids=[r[0] for r in REFUSALS])
def test_apply_refuses_any_mismatch_and_writes_nothing(
    world: dict[str, Path], name: str, change: Any, words: str
) -> None:
    body = change(_decisions(_decision("Cust Ref", "approve", "clients.email")))
    result = _apply(world, body)
    assert result.exit_code == 2, result.output
    assert "Refused" in result.output and words in result.output
    assert not mapping_path(world["mapping"], "crm").exists()


def test_apply_refuses_when_the_drop_no_longer_matches(world: dict[str, Path]) -> None:
    (world["drop"] / "crm.csv").write_text("Client ID,Cust Ref\nC1,R1\n")
    result = _apply(world, _decisions(_decision("Cust Ref", "approve", "clients.email")))
    assert result.exit_code == 2 and "format" in result.output
    assert not world["mapping"].exists()


def test_apply_refuses_a_run_without_a_review_file(world: dict[str, Path]) -> None:
    (world["run"] / "mapping_review.json").unlink()
    result = _apply(world, _decisions(_decision("Cust Ref", "approve", "clients.email")))
    assert result.exit_code == 2 and "mapping_review.json" in result.output


def test_apply_refuses_a_symlinked_mapping_folder(world: dict[str, Path], tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    world["mapping"].symlink_to(elsewhere)
    result = _apply(world, _decisions(_decision("Cust Ref", "approve", "clients.email")))
    assert result.exit_code == 2 and "symlink" in result.output
    assert list(elsewhere.iterdir()) == []


def test_apply_never_echoes_rejected_input(world: dict[str, Path]) -> None:
    body = _decisions(_decision("Cust Ref", "approve", "clients.email"), reviewer="")
    body["decisions"][0]["header"] = "123-45-6789"
    result = _apply(world, body)
    assert result.exit_code == 2 and "123-45-6789" not in result.output


def test_apply_never_carries_entries_saved_for_another_format(world: dict[str, Path]) -> None:
    old = MappingEntry(header="Client ID", table="clients", field="client_id", method="manual",
                       confidence=None, decided_at="2026-09-01T00:00:00+00:00")  # fmt: skip
    other = SourceMapping(source="crm", format_fingerprint="f" * 16, entries=(old,))
    save_mapping(world["mapping"], other)
    result = _apply(world, _decisions(_decision("Cust Ref", "approve", "clients.email")))
    assert result.exit_code == 0, result.output
    saved = load_mapping(world["mapping"], "crm")
    assert saved is not None and saved.format_fingerprint == FP
    entry = saved.entry("Client ID")
    assert entry is not None and entry.method == "unmapped"  # not re-stamped
    previous = load_mapping_text(world["mapping"] / "crm.yaml.prev")
    assert "ffffffffffffffff" in previous


def load_mapping_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_apply_refuses_a_field_another_column_already_holds(world: dict[str, Path]) -> None:
    # "Client ID" maps to clients.client_id by synonym, so a correction to it would collide.
    result = _apply(world, _decisions(_decision("Cust Ref", "correct", "clients.client_id")))
    assert result.exit_code == 2 and "already held by another column" in result.output
    assert not world["mapping"].exists()


def test_apply_refuses_a_field_a_saved_decision_holds(world: dict[str, Path]) -> None:
    held = MappingEntry(header="Client ID", table="clients", field="phone", method="manual",
                        confidence=None, decided_at="2026-09-01T00:00:00+00:00")  # fmt: skip
    save_mapping(world["mapping"], SourceMapping(source="crm", entries=(held,)))
    before = mapping_path(world["mapping"], "crm").read_bytes()
    result = _apply(world, _decisions(_decision("Cust Ref", "correct", "clients.phone")))
    assert result.exit_code == 2 and "already held" in result.output
    assert mapping_path(world["mapping"], "crm").read_bytes() == before


def test_apply_refuses_a_decided_at_with_no_time_zone(world: dict[str, Path]) -> None:
    body = _decisions(
        _decision("Cust Ref", "approve", "clients.email"), decided_at="2026-10-06T15:00:00"
    )
    result = _apply(world, body)
    assert result.exit_code == 2 and "time zone" in result.output


def _two_file_world(world: dict[str, Path]) -> None:
    """A second CRM file with the same headers, listed under the same source."""
    rows = ["C3,1952-01-02,R3,web"]
    (world["drop"] / "crm_feb.csv").write_text(",".join(HEADERS) + "\n" + "\n".join(rows) + "\n")
    files = [
        {"source": "crm", "file_name": "crm.csv", "sheet": None, "rows": 2},
        {"source": "crm", "file_name": "crm_feb.csv", "sheet": None, "rows": 1},
    ]
    (world["drop"] / "manifest.json").write_text(json.dumps({"files": files}))
    second = {**_item("Cust Ref", "clients.email"), "file_name": "crm_feb.csv",
              "item_id": _item_id("crm", "Cust Ref", "crm_feb.csv")}  # fmt: skip
    path = world["run"] / "mapping_review.json"
    review = json.loads(path.read_text())
    review["items"].append(second)
    path.write_text(json.dumps(review))


def test_two_files_under_one_source_must_agree(world: dict[str, Path]) -> None:
    _two_file_world(world)
    first = _decision("Cust Ref", "approve", "clients.email")
    second = {**first, "item_id": _item_id("crm", "Cust Ref", "crm_feb.csv")}
    agree = _apply(world, _decisions(first, second))
    assert agree.exit_code == 0, agree.output
    disagree = _apply(world, _decisions(first, {**second, "action": "ignore", "field": None}))
    assert disagree.exit_code == 2 and "disagrees" in disagree.output


def test_apply_saves_a_roster_column_under_its_sheet_source(tmp_path: Path) -> None:
    from openpyxl import Workbook

    drop = tmp_path / "agency" / "drop"
    drop.mkdir(parents=True)
    book = Workbook()
    agents = book.active
    assert agents is not None
    agents.title = "Agents"
    for row in (["Agent NPN", "Agent Name", "Desk Code"], ["12345678", "Pat Lee", "D1"]):
        agents.append(row)
    book.save(drop / "agent_roster.xlsx")
    files = [{"source": "roster", "file_name": "agent_roster.xlsx", "sheet": "Agents", "rows": 1}]
    (drop / "manifest.json").write_text(json.dumps({"files": files}))
    from intake.ingest import ingest
    from intake.mapping.review import file_label

    [table] = ingest(drop, run_id="t").tables
    headers = [c for c in table.frame.columns if c != "lineage"]
    file_name = file_label(table)
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    item = {**_item("Desk Code", None), "source": "roster_agents", "file_name": file_name,
            "item_id": _item_id("roster_agents", "Desk Code", file_name),
            "format_fingerprint": format_fingerprint(headers),
            "allowed_fields": ["agents.npn", "agents.full_name", "none"]}  # fmt: skip
    review = {"run_id": RUN_ID, "mapping_version": VERSION, "jev_mode": "replay", "items": [item]}
    (run / "mapping_review.json").write_text(json.dumps(review))
    decision = {"item_id": item["item_id"], "source": "roster_agents", "header": "Desk Code",
                "format_fingerprint": item["format_fingerprint"], "action": "ignore",
                "field": None}  # fmt: skip
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(_decisions(decision)))
    args = ["mapping", "apply", str(path), "--run", str(run), "--in", str(drop)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    saved = load_mapping(tmp_path / "agency" / "mapping", "roster_agents")
    assert saved is not None and saved.entry("Desk Code") is not None


def test_a_masked_header_cannot_be_decided_or_matched_by_its_raw_value(tmp_path: Path) -> None:
    raw_header = "Member 123-45-6789"
    masked = "Me**** ***-**-****"
    drop = tmp_path / "agency" / "drop"
    drop.mkdir(parents=True)
    headers = ["Client ID", raw_header]
    (drop / "crm.csv").write_text(",".join(headers) + "\nC1,x1\nC2,x2\n")
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    item = {**_item(masked, None), "item_id": _item_id("crm", masked),
            "format_fingerprint": format_fingerprint(headers)}  # fmt: skip
    review = {"run_id": RUN_ID, "mapping_version": VERSION, "jev_mode": "replay", "items": [item]}
    (run / "mapping_review.json").write_text(json.dumps(review))
    base = {"item_id": item["item_id"], "source": "crm", "header": masked,
            "format_fingerprint": item["format_fingerprint"], "action": "ignore",
            "field": None}  # fmt: skip
    for decision in (base, {**base, "header": raw_header}):
        path = tmp_path / "decisions.json"
        path.write_text(json.dumps(_decisions(decision)))
        args = ["mapping", "apply", str(path), "--run", str(run), "--in", str(drop)]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2, result.output
        assert "6789" not in result.output
    assert not (tmp_path / "agency" / "mapping").exists()


def _two_source_world(world: dict[str, Path]) -> None:
    """The same export dropped again under a second source, enrollment."""
    (world["drop"] / "enroll.csv").write_text((world["drop"] / "crm.csv").read_text())
    files = [
        {"source": "crm", "file_name": "crm.csv", "sheet": None, "rows": 2},
        {"source": "enrollment", "file_name": "enroll.csv", "sheet": None, "rows": 2},
    ]
    (world["drop"] / "manifest.json").write_text(json.dumps({"files": files}))
    item = {**_item("Cust Ref", "clients.email"), "source": "enrollment",
            "file_name": "enroll.csv",
            "item_id": _item_id("enrollment", "Cust Ref", "enroll.csv")}  # fmt: skip
    path = world["run"] / "mapping_review.json"
    review = json.loads(path.read_text())
    review["items"].append(item)
    path.write_text(json.dumps(review))


def test_a_write_that_fails_part_way_names_what_was_written(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from intake.mapping import apply as apply_module

    _two_source_world(world)
    real = apply_module.save_mapping
    calls: list[str] = []

    def flaky(mapping_dir: Path, mapping: SourceMapping) -> Path:
        calls.append(mapping.source)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(mapping_dir, mapping)

    monkeypatch.setattr(apply_module, "save_mapping", flaky)
    first = _decision("Cust Ref", "approve", "clients.email")
    second = {**first, "source": "enrollment",
              "item_id": _item_id("enrollment", "Cust Ref", "enroll.csv")}  # fmt: skip
    result = _apply(world, _decisions(first, second))
    assert result.exit_code == 2, result.output
    assert "Nothing was written" not in result.output
    written = mapping_path(world["mapping"], calls[0])
    assert written.exists() and str(written) in result.output
    assert ".yaml.prev" in result.output
    assert not mapping_path(world["mapping"], calls[1]).exists()


def test_a_problem_found_before_writing_writes_nothing(
    world: dict[str, Path], tmp_path: Path
) -> None:
    _two_source_world(world)
    world["mapping"].mkdir(parents=True)
    (world["mapping"] / "enrollment.yaml").symlink_to(tmp_path / "elsewhere.yaml")
    first = _decision("Cust Ref", "approve", "clients.email")
    second = {**first, "source": "enrollment",
              "item_id": _item_id("enrollment", "Cust Ref", "enroll.csv")}  # fmt: skip
    result = _apply(world, _decisions(first, second))
    assert result.exit_code == 2 and "Nothing was written" in result.output
    assert not mapping_path(world["mapping"], "crm").exists()
