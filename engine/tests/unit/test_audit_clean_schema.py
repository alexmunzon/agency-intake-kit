import json

import pytest
from test_audit_intake_correctness import NOW, base_tables, client, policy

from agency_schema.enums import Severity
from agency_schema.lineage import Lineage
from agency_schema.models import TABLE_MODELS
from agency_schema.outputs import JevMode, RunStatus
from intake.run.canonicalize import FIELDS
from intake.run.clean import LINEAGE_FIELDS, clean_model_records, clean_tables
from intake.run.pipeline import RunOptions, run


def validate_all(clean):
    for table, frame in clean.items():
        for row in frame.iter_rows(named=True):
            fields = {f: row[f] for f in FIELDS[table]}
            for key in ("members", "license_states"):
                if key in fields:
                    fields[key] = tuple(fields[key].split("|")) if fields[key] else ()
            fields["lineage"] = Lineage(**{f: row[f"lineage_{f}"] for f in LINEAGE_FIELDS})
            TABLE_MODELS[table].model_validate(fields)


@pytest.mark.parametrize(
    "field", ["dob", "first_name", "last_name", "address_line1", "city", "state", "zip"]
)
def test_required_client_fields_have_visible_errors_and_exclude_dependents(field):
    tables = base_tables([client(**{field: None})], [policy(), policy("P2")])
    records = clean_model_records(tables, [])
    hit = next(r for r in records if r.field == f"clients.{field}")
    assert hit.rule_id == "MAP-004" and hit.severity == Severity.ERROR
    assert hit.lineage and hit.raw_hash == hit.lineage.raw_hash
    assert hit.row_number == 2 and not hit.blocks_load and hit.value_minimized is None
    clean = clean_tables(tables, records)
    assert not clean["clients"].height and not clean["policies"].height
    validate_all(clean)


def test_policy_error_on_shared_crm_row_does_not_exclude_valid_client():
    tables = base_tables(policy_values=[policy(plan_id=None)])
    records = []
    clean = clean_tables(tables, records)
    assert any(r.field == "policies.plan_id" for r in records)
    assert clean["clients"].height == 1 and clean["policies"].height == 0
    validate_all(clean)


def test_optional_blanks_remain_valid_and_repeat_validation_is_idempotent():
    tables = base_tables()
    records = []
    clean = clean_tables(tables, records)
    assert not records and clean["clients"].height == 1
    validate_all(clean)
    assert clean_model_records(tables, records) == []


@pytest.mark.parametrize(
    "table,field",
    [("agents", "first_name"), ("rts", "effective_date"), ("commission_lines", "amount")],
)
def test_other_declared_required_fields_are_guarded(table, field):
    tables = base_tables()
    if table == "commission_lines":
        from test_audit_intake_correctness import canonical, commission

        tables[table] = canonical(table, [commission()], "statement.csv")
    import polars as pl

    tables[table] = tables[table].with_columns(pl.lit(None, dtype=pl.String).alias(field))
    records = []
    clean = clean_tables(tables, records)
    assert any(r.field == f"{table}.{field}" for r in records)
    assert not clean[table].height
    validate_all(clean)


def test_pipeline_exports_visible_schema_error_before_status(tmp_path):
    import csv

    drop = tmp_path / "drop"
    drop.mkdir()
    row = {
        "Client ID": "C1",
        "First Name": "",
        "Last Name": "Lee",
        "DOB": "1950-01-02",
        "Address": "1 Main",
        "City": "Austin",
        "State": "TX",
        "Zip": "78701",
        "Policy #": "",
        "Carrier": "",
        "Plan": "",
        "Product": "",
        "Eff Date": "",
        "Status": "",
        "Writing Agent NPN": "",
    }
    with (drop / "crm.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    (drop / "manifest.json").write_text(
        json.dumps({"files": [{"source": "crm", "file_name": "crm.csv", "rows": 1}]})
    )
    result = run(RunOptions(drop=drop, out=tmp_path / "run", jev_mode=JevMode.OFF, as_of=NOW))
    assert result.status == RunStatus.PASSED_WITH_WARNINGS
    exported = [
        json.loads(line) for line in (result.run_dir / "exceptions.jsonl").read_text().splitlines()
    ]
    assert any(
        x["rule_id"] == "MAP-004"
        and x["field"] == "clients.first_name"
        and x["lineage"]["row_number"] == 2
        for x in exported
    )
    import polars as pl

    assert pl.read_parquet(result.run_dir / "clean/clients.parquet").height == 0


def test_invalid_agent_excludes_required_dependents_with_visible_evidence():
    import polars as pl

    tables = base_tables()
    tables["agents"] = tables["agents"].with_columns(
        pl.lit(None, dtype=pl.String).alias("first_name")
    )
    records = []
    clean = clean_tables(tables, records)
    assert not clean["agents"].height and not clean["policies"].height and not clean["rts"].height
    assert {r.field for r in records} >= {
        "agents.first_name",
        "policies.writing_agent_npn",
        "rts.npn",
    }
    validate_all(clean)


def test_invalid_typed_value_retains_original_minimized_evidence():
    import polars as pl

    from agency_schema.exceptions import minimize_value

    tables = base_tables()
    tables["rts"] = tables["rts"].with_columns(pl.lit("someday").alias("effective_date"))
    records = []
    clean = clean_tables(tables, records)
    error = next(r for r in records if r.field == "rts.effective_date")
    assert error.value_minimized == minimize_value("someday")
    assert "someday" not in error.message
    assert not clean["rts"].height
