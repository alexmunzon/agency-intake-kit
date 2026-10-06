"""Independent, tiny synthetic repros. Assertions express the required corrected behavior.

Run against captured sources with the parent's isolated Python runner. These tests do not
modify a repository or call models/network services. Several are expected to fail before fixes.
"""

import csv
import json
from datetime import UTC, datetime

import polars as pl

from agency_schema.outputs import JevMode
from intake.checks import run_cross_record_checks
from intake.mapping.enums import normalize_column
from intake.mapping.jev_mapping import Asker
from intake.mapping.synonyms import Target
from intake.readers import build_frame
from intake.rules import run_row_rules
from intake.rules.frames import client_frame, policy_frame
from intake.run.canonicalize import FIELDS, frame_from_rows, households
from intake.run.clean import clean_tables
from intake.run.pipeline import RunOptions, run
from intake.tieout import run_tieout

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)


def canonical(name, values, source_file="crm.csv", first_row=2):
    rows = [{**dict.fromkeys(FIELDS[name]), **v} for v in values]
    return frame_from_rows(source_file, rows, first_row=first_row)


def client(cid="C1", **changes):
    return {
        "client_id": cid,
        "first_name": "Ann",
        "last_name": "Lee",
        "dob": "1950-01-02",
        "address_line1": "1 Main",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
        "household_id": "H1",
        **changes,
    }


def policy(pid="P1", **changes):
    return {
        "policy_id": pid,
        "client_id": "C1",
        "carrier": "Bluepeak",
        "carrier_member_id": "M1",
        "line_of_business": "MA",
        "plan_id": "H1234-001",
        "state": "TX",
        "eligibility_reason": "AGE",
        "effective_date": "2020-01-01",
        "status": "ACTIVE",
        "writing_agent_npn": "111",
        **changes,
    }


def commission(**changes):
    return {
        "carrier": "Bluepeak",
        "statement_period": "2026-06",
        "line_no": "1",
        "carrier_member_id": "M1",
        "agent_npn": "111",
        "amount": "26.25",
        "commission_type": "RENEWAL",
        **changes,
    }


def base_tables(client_values=None, policy_values=None, rts_values=None):
    return {
        "clients": canonical("clients", client_values or [client()]),
        "policies": canonical("policies", policy_values or [policy()]),
        "agents": canonical(
            "agents",
            [
                {
                    "npn": "111",
                    "first_name": "Jo",
                    "last_name": "Ray",
                    "license_states": "TX",
                    "status": "ACTIVE",
                }
            ],
            "roster.xlsx",
        ),
        "rts": canonical(
            "rts",
            rts_values
            or [
                {
                    "npn": "111",
                    "carrier": "Bluepeak",
                    "state": "TX",
                    "plan_year": "2020",
                    "line_of_business": "MA",
                    "appointed": "true",
                    "certified": "true",
                    "effective_date": "2019-01-01",
                }
            ],
            "rts.xlsx",
        ),
    }


def test_client_only_manifest_writes_not_run_result_instead_of_crashing(tmp_path):
    """A valid client-only drop has unavailable reconciliation, and must still write a run."""
    drop = tmp_path / "drop"
    drop.mkdir()
    row = {
        "Client ID": "C1",
        "First Name": "Ann",
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
        json.dumps({"files": [{"source": "crm", "file_name": "crm.csv", "sheet": None, "rows": 1}]})
    )
    result = run(RunOptions(drop=drop, out=tmp_path / "run", jev_mode=JevMode.OFF, as_of=NOW))
    print("OBSERVED client-only", result.status)
    assert (result.run_dir / "scorecard.json").is_file()


def test_household_does_not_reference_an_excluded_client():
    tables = base_tables([client(), client("C2", first_name="Bo", dob="not-a-date")])
    tables["households"] = households(tables["clients"])
    records = run_row_rules(
        client_frame(tables["clients"], NOW.date()),
        policy_frame(tables["policies"], tables["clients"], tables["agents"], NOW.date()),
    )
    clean = clean_tables(tables, records)
    ids = set(clean["clients"]["client_id"])
    members = clean["households"]["members"].item().split("|")
    print("OBSERVED clients", ids, "household members", members)
    assert set(members) <= ids, "clean household still references excluded C2"


def test_rts_with_unreadable_end_is_not_proved_held():
    tables = base_tables(
        rts_values=[
            {
                "npn": "111",
                "carrier": "Bluepeak",
                "state": "TX",
                "plan_year": "2020",
                "line_of_business": "MA",
                "appointed": "true",
                "certified": "true",
                "effective_date": "2019-01-01",
                "end_date": "expired",
            }
        ]
    )
    result = run_cross_record_checks(tables)
    print(
        "OBSERVED malformed end",
        "records",
        [r.rule_id for r in result.records],
        "coverage",
        [c.coverage for c in result.coverage.cells],
        "skipped",
        result.skipped,
    )
    assert any(r.rule_id == "RTS-001" for r in result.records), (
        "malformed end_date grants HELD status"
    )


def test_rts_starting_after_sale_is_not_proved_held():
    tables = base_tables(
        rts_values=[
            {
                "npn": "111",
                "carrier": "Bluepeak",
                "state": "TX",
                "plan_year": "2020",
                "line_of_business": "MA",
                "appointed": "true",
                "certified": "true",
                "effective_date": "2020-07-01",
            }
        ]
    )
    result = run_cross_record_checks(tables)
    print(
        "OBSERVED future RTS start",
        [r.rule_id for r in result.records],
        [c.coverage for c in result.coverage.cells],
    )
    assert any(r.rule_id == "RTS-001" for r in result.records), (
        "2020-07 RTS authorizes 2020-01 policy"
    )


def test_policy_ref_does_not_link_a_different_carrier():
    tables = base_tables()
    tables["commission_lines"] = canonical(
        "commission_lines",
        [commission(carrier="Harborline", carrier_member_id=None, policy_ref="P1")],
        "harborline.xlsx",
    )
    result = run_tieout(tables, run_id="test-run")
    print(
        "OBSERVED foreign carrier",
        result.legs[1].matched,
        result.legs[1].unmatched,
        "unexplained",
        [(r.key, str(r.unexplained_revenue)) for r in result.totals_by_carrier.rows],
    )
    assert result.legs[1].unmatched == 1, "Harborline payment links to Bluepeak policy_ref"


def test_unresolved_policy_status_becomes_schema_valid_unknown():
    tables = base_tables(policy_values=[policy(status="XFER")])
    normalized, decisions = normalize_column(
        pl.Series(["XFER"]), Target("policies", "status"), Asker(None)
    )
    tables["policies"] = tables["policies"].with_columns(normalized.alias("status"))
    records = run_row_rules(
        client_frame(tables["clients"], NOW.date()),
        policy_frame(tables["policies"], tables["clients"], tables["agents"], NOW.date()),
    )
    clean = clean_tables(tables, records)
    print(
        "OBSERVED status",
        clean["policies"]["status"].to_list(),
        "rules",
        [r.rule_id for r in records],
        "decision",
        decisions[0].reason,
    )
    assert clean["policies"]["status"].item() == "UNKNOWN", (
        "clean status is XFER despite STA-001 fix promise"
    )


def test_reader_does_not_discard_surplus_cells_from_hash():
    a = build_frame(
        ["ID", "Amount"],
        [(2, ["P1", "26.25", "extra-A"])],
        source_file="t.csv",
        sheet=None,
        run_id="r",
        mapping_version="raw",
    )
    b = build_frame(
        ["ID", "Amount"],
        [(2, ["P1", "26.25", "extra-B"])],
        source_file="t.csv",
        sheet=None,
        run_id="r",
        mapping_version="raw",
    )
    print(
        "OBSERVED surplus hashes equal",
        a["lineage"].item()["raw_hash"] == b["lineage"].item()["raw_hash"],
    )
    assert a["lineage"].item()["raw_hash"] != b["lineage"].item()["raw_hash"], (
        "distinct raw rows hash equally"
    )
