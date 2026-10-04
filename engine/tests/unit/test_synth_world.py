import csv
import hashlib
import json
from collections import Counter
from datetime import date
from functools import cache
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agency_schema.enums import LineOfBusiness, PolicyStatus
from agency_schema.formats import (
    is_valid_hios_plan_id,
    is_valid_mbi,
    is_valid_medigap_letter,
    is_valid_npn,
    normalize_email,
    normalize_name,
    normalize_phone,
    parse_medicare_plan_id,
    zip3_matches_state,
)
from agency_schema.models import TABLE_MODELS
from synth_agency_data.canonical_writer import write_world
from synth_agency_data.cli import app
from synth_agency_data.rates import expected_amount
from synth_agency_data.world import AS_OF, STATEMENT_PERIODS, World, build_world

MEDICARE = {LineOfBusiness.MA, LineOfBusiness.PDP, LineOfBusiness.MEDSUPP}


@cache
def world() -> World:
    return build_world(seed=42, n_clients=2000)


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _dir_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_counts_and_mix() -> None:
    t = world().tables
    assert len(t["clients"]) == 2000
    assert len(t["policies"]) == 2600
    assert len(t["agents"]) == 25
    assert 1300 <= len(t["households"]) <= 1500
    mix = Counter(p["line_of_business"] for p in t["policies"])
    assert mix == {"MA": 1430, "PDP": 390, "MEDSUPP": 260, "ACA": 520}
    assert len({p["carrier"] for p in t["policies"]}) == 6


def test_same_seed_is_byte_identical(tmp_path: Path) -> None:
    write_world(build_world(seed=7, n_clients=150), tmp_path / "a")
    write_world(build_world(seed=7, n_clients=150), tmp_path / "b")
    write_world(build_world(seed=8, n_clients=150), tmp_path / "c")
    assert _dir_digest(tmp_path / "a") == _dir_digest(tmp_path / "b")
    assert _dir_digest(tmp_path / "a") != _dir_digest(tmp_path / "c")


def test_written_rows_validate_against_models(tmp_path: Path) -> None:
    write_world(world(), tmp_path)
    for table, model in TABLE_MODELS.items():
        path = tmp_path / "canonical" / f"{table}.csv"
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(world().tables[table])
        assert list(rows[0]) == [k for k in model.model_fields if k != "lineage"]
        for i, row in enumerate(world().tables[table]):
            lineage = {
                "source_file": f"canonical/{table}.csv",
                "sheet": None,
                "row_number": i + 2,
                "raw_hash": "0" * 64,
                "run_id": "synth-test",
                "mapping_version": "canonical",
            }
            model.model_validate({**row, "lineage": lineage})
    truth = json.loads((tmp_path / "ground_truth.json").read_text())
    assert truth["seed"] == 42 and truth["defects"] == []


def test_referential_integrity() -> None:
    t = world().tables
    clients = {c["client_id"]: c for c in t["clients"]}
    npns = {a["npn"] for a in t["agents"]}
    assert all(p["client_id"] in clients for p in t["policies"])
    assert all(p["writing_agent_npn"] in npns for p in t["policies"])
    assert all(a["upline_npn"] is None or a["upline_npn"] in npns for a in t["agents"])
    assert sum(a["upline_npn"] is None for a in t["agents"]) == 1
    members = [m for h in t["households"] for m in h["members"]]
    assert sorted(members) == sorted(clients)
    assert all(
        clients[m]["household_id"] == h["household_id"]
        for h in t["households"]
        for m in h["members"]
    )
    assert len({p["policy_id"] for p in t["policies"]}) == len(t["policies"])


def test_every_value_passes_the_format_helpers() -> None:
    t = world().tables
    for c in t["clients"]:
        assert zip3_matches_state(c["zip"], c["state"])
        assert c["phone"] is None or normalize_phone(c["phone"]) is not None
        assert c["email"] is None or normalize_email(c["email"]) == c["email"]
        assert c["mbi"] is None or is_valid_mbi(c["mbi"])
    assert all(is_valid_npn(a["npn"]) for a in t["agents"])
    for p in t["policies"]:
        lob = LineOfBusiness(p["line_of_business"])
        if lob in (LineOfBusiness.MA, LineOfBusiness.PDP):
            parsed = parse_medicare_plan_id(p["plan_id"])
            assert parsed is not None and parsed.line_of_business == lob
        elif lob == LineOfBusiness.MEDSUPP:
            assert is_valid_medigap_letter(p["plan_id"])
        else:
            assert is_valid_hios_plan_id(p["plan_id"])


def test_people_and_dates_are_consistent() -> None:
    t = world().tables
    clients = {c["client_id"]: c for c in t["clients"]}
    keys = [(normalize_name(f"{c['first_name']} {c['last_name']}"), c["dob"]) for c in t["clients"]]
    assert len(set(keys)) == len(keys)  # no DUP-002 in the clean world
    for p in t["policies"]:
        c = clients[p["client_id"]]
        lob = LineOfBusiness(p["line_of_business"])
        assert p["state"] == c["state"]
        assert (c["mbi"] is not None) == (lob in MEDICARE)
        if lob in MEDICARE:
            assert p["effective_date"].day == 1
            if p["eligibility_reason"] == "AGE":
                assert _age(c["dob"], p["effective_date"]) >= 65
            else:
                assert p["eligibility_reason"] in ("DISABILITY", "ESRD")
                assert _age(c["dob"], p["effective_date"]) < 65
        else:
            assert p["eligibility_reason"] is None
            assert 20 <= _age(c["dob"], AS_OF) <= 64
        term = p["termination_date"]
        assert term is None or term > p["effective_date"]
        if p["status"] == PolicyStatus.ACTIVE:
            assert term is None and p["effective_date"] <= AS_OF
        elif p["status"] == PolicyStatus.TERMINATED:
            assert term is not None and term < date(2026, 6, 1)
        else:
            assert p["status"] == PolicyStatus.PENDING and p["effective_date"] > AS_OF
    ages = [_age(c["dob"], AS_OF) for c in t["clients"] if c["mbi"]]
    assert max(ages) <= 92


def test_every_writing_agent_has_rts_and_license() -> None:
    t = world().tables
    rts = {
        (r["npn"], r["carrier"], r["state"], r["plan_year"], r["line_of_business"])
        for r in t["rts"]
    }
    licenses = {a["npn"]: set(a["license_states"]) for a in t["agents"]}
    assert all(r["end_date"] is None and r["appointed"] and r["certified"] for r in t["rts"])
    for p in t["policies"]:
        npn, state = p["writing_agent_npn"], p["state"]
        assert state in licenses[npn]
        last = p["termination_date"] or max(p["effective_date"], AS_OF)
        for year in range(p["effective_date"].year, last.year + 1):
            assert (npn, p["carrier"], state, year, p["line_of_business"]) in rts


def test_statements_pay_every_active_policy_on_schedule() -> None:
    t = world().tables
    assert sorted({ln["statement_period"] for ln in t["commission_lines"]}) == list(
        STATEMENT_PERIODS
    )
    paid = Counter((ln["policy_ref"], ln["statement_period"]) for ln in t["commission_lines"])
    active = [p for p in t["policies"] if p["status"] == PolicyStatus.ACTIVE]
    assert len(paid) == len(t["commission_lines"]) == 3 * len(active)
    policies = {p["policy_id"]: p for p in t["policies"]}
    for ln in t["commission_lines"]:
        p = policies[ln["policy_ref"]]
        assert p["status"] == PolicyStatus.ACTIVE
        assert ln["carrier"] == p["carrier"] and ln["carrier_member_id"] == p["carrier_member_id"]
        assert ln["amount"] == expected_amount(
            p["line_of_business"], p["effective_date"], ln["statement_period"]
        )
    keys = [(ln["carrier"], ln["statement_period"], ln["line_no"]) for ln in t["commission_lines"]]
    assert len(set(keys)) == len(keys)
    total = sum(ln["amount"] for ln in t["commission_lines"])
    expected = sum(
        expected_amount(p["line_of_business"], p["effective_date"], period)
        for p in active
        for period in STATEMENT_PERIODS
    )
    assert total == expected


def test_no_real_carrier_names() -> None:
    carriers = {p["carrier"] for p in world().tables["policies"]}
    assert carriers == {
        "Northwind Health",
        "Bluepeak",
        "Harborline",
        "Cardinal Mutual",
        "Summit Health Plans",
        "Meridian Care",
    }


@pytest.mark.parametrize("n_clients", [0, -5])
def test_refuses_empty_world(n_clients: int) -> None:
    with pytest.raises(ValueError):
        build_world(seed=1, n_clients=n_clients)


def test_cli_generate(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["generate", "--seed", "3", "--clients", "60", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "canonical" / "policies.csv").exists()
    assert (tmp_path / "ground_truth.json").exists()
