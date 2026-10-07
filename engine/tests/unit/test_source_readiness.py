"""Readiness must describe expected coverage, never infer it from deliveries."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from intake.source_readiness import ReadinessPackage, evaluate, import_package


def package() -> dict:
    content = "synthetic statement\namount\n10.00\n"
    sha = hashlib.sha256(content.encode()).hexdigest()
    return {
        "artifact_type": "source_readiness",
        "schema_version": "1.0.0",
        "data_kind": "synthetic",
        "agency_id": "agency-synthetic",
        "intake_run_id": None,
        "run_id": "synthetic-readiness-1",
        "as_of": "2026-10-07T12:00:00Z",
        "expected_inventory": [
            {
                "agency_id": "agency-synthetic",
                "carrier": "Harborline",
                "file_type": "statement",
                "period": "2026-09",
                "minimum_source_date": "2026-09-30",
                "owner": "Synthetic operations",
                "next_action": "Review source evidence",
            }
        ],
        "versions": [
            {
                "version_id": "v1",
                "agency_id": "agency-synthetic",
                "carrier": "Harborline",
                "file_type": "statement",
                "period": "2026-09",
                "source_date": "2026-09-30",
                "file_name": "statement.csv",
                "file_sha256": sha,
                "supersedes_version_id": None,
            }
        ],
        "receipts": [
            {
                "receipt_id": "r1",
                "version_id": "v1",
                "received_at": "2026-10-01T12:00:00Z",
                "owner": "Synthetic operations",
                "next_action": "Review source evidence",
            }
        ],
        "evidence": [{"sha256": sha, "content": content}],
    }


def summary(data: dict):
    return evaluate(ReadinessPackage.model_validate(data))


def test_inventory_absent_or_empty_is_unknown_never_complete():
    for inventory in (None, []):
        data = package()
        data["expected_inventory"] = inventory
        result = summary(data)
        assert result.state == "unknown"
        assert result.complete is False
        assert result.expected_count == 0


@pytest.mark.parametrize(
    ("change", "state"),
    [
        ({"period": "2026-08"}, "missing"),
        ({"source_date": None}, "unknown"),
        ({"source_date": "2026-09-29"}, "stale"),
        ({"source_date": "2026-09-30"}, "current"),
    ],
)
def test_period_and_source_date(change, state):
    data = package()
    data["versions"][0].update(change)
    result = summary(data)
    assert result.entries[0].state == state
    assert result.complete == (state == "current")
    assert result.unexpected_version_ids == (["v1"] if state == "missing" else [])


def test_unknown_freshness_policy_and_missing_receipt():
    data = package()
    data["expected_inventory"][0]["minimum_source_date"] = None
    assert summary(data).state == "unknown"
    data["receipts"] = []
    assert summary(data).state == "missing"


def test_duplicate_receipts_retained_without_coverage_inflation():
    data = package()
    data["receipts"].append(dict(data["receipts"][0], receipt_id="r2"))
    result = summary(data)
    assert result.current_count == 1
    assert result.receipt_count == 2
    assert result.duplicate_receipt_count == 1
    assert len(ReadinessPackage.model_validate(data).receipts) == 2


def correction(data, version="v2", target="v1", content="synthetic correction\n20.00\n"):
    sha = hashlib.sha256(content.encode()).hexdigest()
    data["evidence"].append({"sha256": sha, "content": content})
    data["versions"].append(
        dict(data["versions"][0], version_id=version, file_sha256=sha, supersedes_version_id=target)
    )
    data["receipts"].append(
        dict(
            data["receipts"][0],
            receipt_id="r-" + version,
            version_id=version,
            received_at="2026-10-02T12:00:00Z",
        )
    )


def test_correction_preserves_old_evidence_and_duplicate_cannot_resurrect_it():
    data = package()
    correction(data)
    data["receipts"].append(
        dict(data["receipts"][0], receipt_id="late-duplicate", received_at="2026-10-03T12:00:00Z")
    )
    result = summary(data)
    assert result.complete
    assert result.entries[0].active_version_ids == ["v2"]
    assert result.superseded_version_ids == ["v1"]
    assert len(ReadinessPackage.model_validate(data).evidence) == 2


def test_competing_corrections_stay_conflicting():
    data = package()
    correction(data)
    correction(data, "v3", content="synthetic competing correction\n30.00\n")
    result = summary(data)
    assert result.state == "conflicting"
    assert result.complete is False
    assert result.entries[0].active_version_ids == ["v2", "v3"]


def test_independent_versions_with_different_bytes_conflict():
    data = package()
    correction(data, target=None)
    assert summary(data).state == "conflicting"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["evidence"][0].update(content="tampered"),
        lambda d: d["versions"][0].update(supersedes_version_id="absent"),
        lambda d: d["versions"][0].update(supersedes_version_id="v1"),
        lambda d: d["versions"][0].update(period="2026-13"),
        lambda d: d["versions"][0].update(source_date="2026-02-30"),
        lambda d: d["receipts"][0].update(received_at="2026-10-01T12:00:00"),
        lambda d: d["receipts"][0].update(received_at="2027-10-01T12:00:00Z"),
        lambda d: d["expected_inventory"].append(copy.deepcopy(d["expected_inventory"][0])),
        lambda d: d["receipts"].append(copy.deepcopy(d["receipts"][0])),
        lambda d: d.update(complete=True),
    ],
)
def test_failed_import_preserves_previous_valid_state(tmp_path: Path, mutation):
    valid = json.dumps(package())
    destination = tmp_path / "saved.json"
    import_package(valid, destination)
    before = destination.read_bytes()
    bad = package()
    mutation(bad)
    with pytest.raises(ValueError):
        import_package(json.dumps(bad), destination)
    assert destination.read_bytes() == before


def test_duplicate_json_keys_refused_and_deterministic_roundtrip(tmp_path: Path):
    destination = tmp_path / "saved.json"
    import_package(json.dumps(package()), destination)
    before = destination.read_bytes()
    import_package(before.decode(), destination)
    assert destination.read_bytes() == before
    with pytest.raises(ValueError):
        import_package(
            before.decode().replace(
                '"schema_version": "1.0.0"', '"schema_version": "1.0.0", "schema_version": "1.0.0"'
            ),
            destination,
        )
    assert destination.read_bytes() == before


def test_onboarding_preserves_every_version_and_uses_verified_contract_pins(tmp_path):
    from zipfile import ZipFile

    from intake.source_readiness_export import export_package

    data = package()
    correction(data)
    model = ReadinessPackage.model_validate(data)
    export_package(model, tmp_path / "one.zip")
    export_package(model, tmp_path / "two.zip")
    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()
    with ZipFile(tmp_path / "one.zip") as archive:
        manifest = json.loads(archive.read("onboarding_manifest.json"))
        assert manifest["schema_version"] == "1.0.0"
        assert manifest["intake_run_id"] is None  # pre-intake, not an invented run
        assert manifest["review_state"] == "not_reviewed"
        for pin in manifest["artifacts"]:
            raw = archive.read(pin["path"])
            assert len(raw) == pin["size_bytes"]
            assert hashlib.sha256(raw).hexdigest() == pin["sha256"]
        saved = ReadinessPackage.model_validate_json(archive.read("source_readiness.json"))
        assert saved == model
    with pytest.raises(FileExistsError):
        export_package(model, tmp_path / "one.zip")


def test_correction_does_not_cross_agencies_or_periods():
    data = package()
    correction(data)
    data["versions"][1]["period"] = "2026-08"
    with pytest.raises(ValueError):
        summary(data)
    data["versions"][1]["period"] = "2026-09"
    data["versions"][1]["agency_id"] = "another-agency"
    with pytest.raises(ValueError):
        summary(data)


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_write_failure_preserves_previous_valid_state(tmp_path, monkeypatch, operation):
    import intake.source_readiness as readiness

    destination = tmp_path / "valid.json"
    import_package(json.dumps(package()), destination)
    original = destination.read_bytes()

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(readiness.os, operation, fail)
    with pytest.raises(OSError):
        import_package(json.dumps(package()), destination)
    assert destination.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["valid.json"]


def test_scoped_cli_roundtrip_and_failed_import(tmp_path):
    from typer.testing import CliRunner

    from intake.source_readiness_cli import app

    runner = CliRunner()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(package()))
    state = tmp_path / "state.json"
    assert runner.invoke(app, ["check", str(source)]).exit_code == 0
    assert runner.invoke(app, ["import", str(source), "--out", str(state)]).exit_code == 0
    before = state.read_bytes()
    source.write_text("{bad json")
    result = runner.invoke(app, ["import", str(source), "--out", str(state)])
    assert result.exit_code != 0
    assert state.read_bytes() == before
    assert (
        runner.invoke(app, ["export", str(state), "--out", str(tmp_path / "out.zip")]).exit_code
        == 0
    )


def test_same_evidence_under_alias_does_not_resurrect_superseded_version():
    data = package()
    data["versions"].append(dict(data["versions"][0], version_id="alias"))
    data["receipts"].append(
        dict(data["receipts"][0], receipt_id="alias-delivery", version_id="alias")
    )
    correction(data)
    result = summary(data)
    assert result.complete
    assert result.entries[0].active_version_ids == ["v2"]
    assert result.superseded_version_ids == ["alias", "v1"]


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-01T24:00:00Z",
        "2026-10-01T12:60:00Z",
        "2026-10-01T12:00:60Z",
        "2026-10-01T12:00:00+24:00",
    ],
)
def test_invalid_clock_refused(value):
    data = package()
    data["receipts"][0]["received_at"] = value
    with pytest.raises(ValueError):
        summary(data)


def test_correction_aliases_with_alias_parents_remain_superseded():
    data = package()
    data["versions"].append(dict(data["versions"][0], version_id="alias-v1"))
    data["receipts"].append(dict(data["receipts"][0], receipt_id="alias-r1", version_id="alias-v1"))
    correction(data)
    data["versions"].append(
        dict(data["versions"][2], version_id="alias-v2", supersedes_version_id="alias-v1")
    )
    data["receipts"].append(
        dict(data["receipts"][-1], receipt_id="alias-r2", version_id="alias-v2")
    )
    correction(data, "v3", target="v2", content="synthetic final correction\n30.00\n")
    result = summary(data)
    assert result.complete
    assert result.entries[0].active_version_ids == ["v3"]
    assert result.superseded_version_ids == ["alias-v1", "alias-v2", "v1", "v2"]
    assert result.duplicate_receipt_count == 2
    # The result must not depend on import array order or receipt timestamps.
    data["versions"].reverse()
    data["receipts"].reverse()
    assert summary(data) == result


def test_same_byte_correction_does_not_supersede_itself():
    data = package()
    data["versions"].append(dict(data["versions"][0], version_id="v2", supersedes_version_id="v1"))
    data["receipts"].append(dict(data["receipts"][0], receipt_id="r2", version_id="v2"))
    result = summary(data)
    assert result.complete
    assert result.entries[0].active_version_ids == ["v2"]
    assert result.superseded_version_ids == ["v1"]


def test_undelivered_correction_cannot_supersede_and_independent_branch_stays_conflicting():
    data = package()
    correction(data)
    data["receipts"].pop()
    result = summary(data)
    assert result.entries[0].active_version_ids == ["v1"]
    assert result.superseded_version_ids == []
    correction(data, "independent", target=None, content="synthetic independent\n30.00\n")
    correction(data, "v3", target="v2", content="synthetic final\n40.00\n")
    result = summary(data)
    assert result.state == "conflicting"
    assert result.entries[0].active_version_ids == ["independent", "v3"]
    assert result.superseded_version_ids == ["v1", "v2"]


@pytest.mark.parametrize("source", ["null", "[]", '"text"', "{", '{"as_of": NaN}'])
def test_malformed_json_shapes_preserve_previous_snapshot(tmp_path, source):
    destination = tmp_path / "state.json"
    import_package(json.dumps(package()), destination)
    original = destination.read_bytes()
    with pytest.raises(ValueError):
        import_package(source, destination)
    assert destination.read_bytes() == original


@pytest.mark.parametrize("field", ["source_date", "minimum_source_date"])
@pytest.mark.parametrize("value", [20260930, "20260930", "2026-09-30T00:00:00Z", "2026-9-30"])
def test_source_dates_and_cutoffs_are_explicit_iso_dates(field, value):
    data = package()
    collection = "versions" if field == "source_date" else "expected_inventory"
    data[collection][0][field] = value
    with pytest.raises(ValueError):
        summary(data)


def test_datetime_source_date_cannot_be_silently_truncated():
    from datetime import datetime

    data = package()
    data["versions"][0]["source_date"] = datetime(2026, 9, 30)
    with pytest.raises(ValueError):
        summary(data)


def test_receipt_microsecond_after_clock_is_rejected():
    data = package()
    data["as_of"] = "2026-10-07T12:00:00.000000Z"
    data["receipts"][0]["received_at"] = "2026-10-07T12:00:00.000001Z"
    with pytest.raises(ValueError):
        summary(data)


def test_unpaired_surrogate_evidence_cannot_be_replacement_encoded():
    data = package()
    data["evidence"][0]["content"] = "\ud800"
    data["evidence"][0]["sha256"] = hashlib.sha256("\ufffd".encode()).hexdigest()
    data["versions"][0]["file_sha256"] = data["evidence"][0]["sha256"]
    with pytest.raises(ValueError):
        summary(data)


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_failed_export_leaves_no_partial_archive(tmp_path, monkeypatch, operation):
    import intake.source_readiness_export as exporter

    def fail(*args):
        raise OSError("simulated export disk failure")

    monkeypatch.setattr(exporter.os, operation, fail)
    with pytest.raises(OSError):
        exporter.export_package(ReadinessPackage.model_validate(package()), tmp_path / "out.zip")
    assert list(tmp_path.iterdir()) == []


def test_export_refuses_symlink_and_generates_safe_provenance_paths(tmp_path):
    from zipfile import ZipFile

    from intake.source_readiness_export import export_package

    data = package()
    data["versions"][0]["file_name"] = "../../outside.csv"
    data["run_id"] = "synthetic-source-producer"
    data["intake_run_id"] = "synthetic-intake-link"
    model = ReadinessPackage.model_validate(data)
    destination = tmp_path / "out.zip"
    export_package(model, destination)
    with ZipFile(destination) as archive:
        manifest = json.loads(archive.read("onboarding_manifest.json"))
        assert manifest["agency_id"] == data["agency_id"]
        assert manifest["run_id"] == data["run_id"]
        assert manifest["intake_run_id"] == data["intake_run_id"]
        assert {pin["path"] for pin in manifest["artifacts"]} == (
            set(archive.namelist()) - {"onboarding_manifest.json"}
        )
        assert all(".." not in path and not path.startswith("/") for path in archive.namelist())
        saved = json.loads(archive.read("source_readiness.json"))
        assert saved["versions"][0]["file_name"] == "../../outside.csv"
    link = tmp_path / "existing-link.zip"
    link.symlink_to(destination)
    original = destination.read_bytes()
    with pytest.raises(FileExistsError):
        export_package(model, link)
    assert destination.read_bytes() == original
    assert link.is_symlink()


@pytest.mark.parametrize(
    "change", ["version_edit", "version_delete", "receipt_edit", "receipt_delete"]
)
def test_same_run_import_cannot_rewrite_or_drop_history(tmp_path, change):
    destination = tmp_path / "state.json"
    data = package()
    import_package(json.dumps(data), destination)
    before = destination.read_bytes()
    if change == "version_edit":
        data["versions"][0]["file_name"] = "renamed.csv"
    elif change == "version_delete":
        data["versions"] = []
        data["receipts"] = []
    elif change == "receipt_edit":
        data["receipts"][0]["owner"] = "Rewritten receiver"
    else:
        data["receipts"] = []
    # These are valid stand-alone snapshots; continuity is what must refuse them.
    ReadinessPackage.model_validate(data)
    with pytest.raises(ValueError, match="must retain every original"):
        import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before


def test_same_run_import_retains_even_unreferenced_original_evidence(tmp_path):
    destination = tmp_path / "state.json"
    data = package()
    original_content = "synthetic unparsed supplemental evidence\n"
    data["evidence"].append(
        {
            "sha256": hashlib.sha256(original_content.encode()).hexdigest(),
            "content": original_content,
        }
    )
    import_package(json.dumps(data), destination)
    before = destination.read_bytes()
    data["evidence"].pop()
    ReadinessPackage.model_validate(data)
    with pytest.raises(ValueError, match="original evidence"):
        import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before


def test_same_run_import_appends_correction_and_duplicate_receipt_with_planning_edits(tmp_path):
    destination = tmp_path / "state.json"
    data = package()
    import_package(json.dumps(data), destination)
    correction(data)
    data["receipts"].append(dict(data["receipts"][0], receipt_id="r-duplicate"))
    data["as_of"] = "2026-10-08T12:00:00Z"
    data["intake_run_id"] = "synthetic-intake-link"
    data["expected_inventory"][0]["owner"] = "New planning owner"
    data["expected_inventory"][0]["next_action"] = "Review corrected file"
    data["expected_inventory"].append(
        dict(data["expected_inventory"][0], carrier="Northwind", next_action="Request statement")
    )
    incoming = import_package(json.dumps(data), destination)
    result = evaluate(incoming)
    assert len(incoming.versions) == 2
    assert result.receipt_count == 3 and result.duplicate_receipt_count == 1
    assert result.entries[0].active_version_ids == ["v2"]
    assert result.superseded_version_ids == ["v1"]
    assert result.entries[1].state == "missing"
    before = destination.read_bytes()
    import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before
    # History arrays can be reordered without changing an existing record.
    for field in ("versions", "receipts", "evidence"):
        data[field].reverse()
    assert import_package(json.dumps(data), destination).run_id == incoming.run_id


@pytest.mark.parametrize("link", [None, "another-intake-run"])
def test_same_run_intake_link_cannot_be_unlinked_or_reassigned(tmp_path, link):
    destination = tmp_path / "state.json"
    data = package()
    data["intake_run_id"] = "synthetic-intake-link"
    import_package(json.dumps(data), destination)
    before = destination.read_bytes()
    data["intake_run_id"] = link
    with pytest.raises(ValueError, match="Intake run link"):
        import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before


def test_same_run_clock_cannot_move_backward_but_equivalent_timezone_is_allowed(tmp_path):
    destination = tmp_path / "state.json"
    data = package()
    import_package(json.dumps(data), destination)
    data["as_of"] = "2026-10-07T07:00:00-05:00"
    import_package(json.dumps(data), destination)
    before = destination.read_bytes()
    data["as_of"] = "2026-10-07T06:59:59.999999-05:00"
    with pytest.raises(ValueError, match="clock backward"):
        import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before


@pytest.mark.parametrize("switch", ["agency", "run"])
def test_explicit_package_switch_can_replace_history(tmp_path, switch):
    destination = tmp_path / "state.json"
    data = package()
    data["intake_run_id"] = "old-intake-link"
    import_package(json.dumps(data), destination)
    data["versions"] = []
    data["receipts"] = []
    data["evidence"] = []
    data["as_of"] = "2026-10-01T12:00:00Z"
    data["intake_run_id"] = None
    if switch == "agency":
        data["agency_id"] = "another-synthetic-agency"
        data["expected_inventory"][0]["agency_id"] = data["agency_id"]
    else:
        data["run_id"] = "another-synthetic-run"
    saved = import_package(json.dumps(data), destination)
    assert saved.versions == saved.receipts == saved.evidence == ()
    assert evaluate(saved).state == "missing"


@pytest.mark.parametrize("previous", ["{corrupt json", "null", '{"unexpected": true}'])
def test_corrupt_existing_store_refuses_replacement_even_for_another_run(tmp_path, previous):
    destination = tmp_path / "state.json"
    destination.write_text(previous)
    before = destination.read_bytes()
    data = package()
    data["run_id"] = "another-synthetic-run"
    with pytest.raises(ValueError):
        import_package(json.dumps(data), destination)
    assert destination.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


def test_cli_refuses_valid_standalone_snapshot_that_discards_same_run_history(tmp_path):
    from typer.testing import CliRunner

    from intake.source_readiness_cli import app

    destination = tmp_path / "state.json"
    import_package(json.dumps(package()), destination)
    before = destination.read_bytes()
    data = package()
    data["receipts"] = []
    source = tmp_path / "incoming.json"
    source.write_text(json.dumps(data))
    result = CliRunner().invoke(app, ["import", str(source), "--out", str(destination)])
    assert result.exit_code != 0
    assert "previous snapshot preserved" in result.output
    assert destination.read_bytes() == before
