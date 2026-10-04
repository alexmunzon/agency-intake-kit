import copy
import csv
import hashlib
import json
import random
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from agency_schema.enums import LineOfBusiness as Lob
from agency_schema.enums import PolicyStatus
from agency_schema.formats import (
    is_valid_hios_plan_id,
    is_valid_mbi,
    is_valid_medigap_letter,
    is_valid_npn,
    normalize_name,
    parse_medicare_plan_id,
    zip3_matches_state,
)
from synth_agency_data.canonical_writer import load_ground_truth, write_world
from synth_agency_data.cli import app
from synth_agency_data.injectors import INJECTORS, Defect, inject, lock_key
from synth_agency_data.planted import ORPHAN_LINE, PLANTED_NPN, PLANTED_POLICY, plant
from synth_agency_data.rates import expected_amount
from synth_agency_data.world import AS_OF, World, build_world

FIXTURE = Path(__file__).parents[3] / "fixtures" / "agency-a"
# Guide 7.3 defaults: defect type -> (allowed rule ids, scored).
EXPECTED: dict[str, tuple[set[str], bool]] = {
    "zip_state_mismatch": ({"ADR-002"}, True),
    "invalid_mbi": ({"MBI-001"}, True),
    "missing_mbi": ({"MBI-003"}, True),
    "npn_malformed": ({"NPN-001"}, True),
    "unknown_writing_agent": ({"NPN-002"}, True),
    "plan_id_malformed": ({"PLN-001", "PLN-002", "PLN-004"}, True),
    "term_before_effective": ({"DAT-002"}, True),
    "status_date_conflict": ({"DAT-003"}, True),
    "messy_status": ({"STA-001"}, True),
    "exact_duplicate_row": ({"DUP-001"}, True),
    "duplicate_policy_id": ({"DUP-003"}, True),
    "orphan_policy": ({"REF-001"}, True),
    "orphan_commission_line": ({"TIE-002"}, True),
    "missing_commission_line": ({"TIE-001"}, True),
    "commission_off_schedule": ({"TIE-003"}, True),
    "crm_status_conflict": ({"TIE-004"}, True),
    "rts_gap": ({"RTS-001"}, True),
    "rts_expired": ({"RTS-002"}, True),
    "license_gap": ({"LIC-001"}, True),
    "name_typo": (set(), False),
    "nickname": (set(), False),
    "dob_transposition": (set(), False),
    "dob_month_day_swap": (set(), False),
    "name_dob_collision": ({"DUP-002"}, True),
    "near_duplicate_client": (set(), False),
}
KEYS = ({"policy_id"}, {"client_id"}, {"npn"}, {"carrier", "statement_period", "line_no"})
MEDICARE = {Lob.MA, Lob.PDP, Lob.MEDSUPP}


@cache
def clean() -> World:
    return build_world(seed=42, n_clients=2000)


@cache
def planted() -> tuple[World, tuple[Defect, ...]]:
    world, defects = plant(clean())
    return world, tuple(defects)


@cache
def injected() -> tuple[World, tuple[Defect, ...]]:
    world, defects = inject(clean())
    return world, tuple(defects)


def _digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _rows(world: World, d: Defect) -> list[dict[str, Any]]:
    key = d["record_key"]
    return [r for r in world.tables[d["source"]] if all(r[k] == v for k, v in key.items())]


def test_injector_list_matches_the_guide() -> None:
    assert [fn.__name__ for fn, _ in INJECTORS] == list(EXPECTED)


@pytest.mark.parametrize(("fn", "rate"), INJECTORS, ids=[fn.__name__ for fn, _ in INJECTORS])
def test_each_injector_labels_defects_without_mutating(fn: Any, rate: float) -> None:
    world = planted()[0]
    before = copy.deepcopy(world.tables)
    out, defects = fn(world, random.Random(1), rate)
    assert world.tables == before  # the input world is never changed
    assert defects, f"{fn.__name__} injected nothing at its default rate"
    rule_ids, scored = EXPECTED[fn.__name__]
    for d in defects:
        assert d["defect_type"] == fn.__name__ and d["scored"] is scored
        assert set(d["expected_rule_ids"]) <= rule_ids
        assert len(d["expected_rule_ids"]) == (1 if scored else 0)
        assert set(d["record_key"]) in KEYS
        assert d["source"] in out.tables and d["row_ref"] is None
        assert lock_key(d["record_key"]) not in world.locked
        assert _rows(out, d), f"{d['record_key']} is not in {d['source']}"


def _paid(world: World) -> dict[tuple[str, str], list[dict[str, Any]]]:
    paid: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ln in world.tables["commission_lines"]:
        paid.setdefault((ln["policy_ref"], ln["statement_period"]), []).append(ln)
    return paid


def _rts_combos(world: World) -> set[tuple[Any, ...]]:
    return {
        (r["npn"], r["carrier"], r["state"], r["line_of_business"]) for r in world.tables["rts"]
    }


def _witnesses(world: World) -> dict[str, Callable[[dict[str, Any], Defect], bool]]:
    """For each defect type, a check that the defect is really in the injected row."""
    t = world.tables
    clients = {c["client_id"]: c for c in t["clients"]}
    npns = {a["npn"]: a for a in t["agents"]}
    member_ids = {p["carrier_member_id"] for p in t["policies"]}
    policy_counts = Counter(p["policy_id"] for p in t["policies"])
    medicare_clients = {p["client_id"] for p in t["policies"] if p["line_of_business"] in MEDICARE}
    paid, combos = _paid(world), _rts_combos(world)
    people = Counter(
        (normalize_name(f"{c['first_name']} {c['last_name']}"), c["dob"]) for c in t["clients"]
    )

    def plan_ok(p: dict[str, Any]) -> bool:
        lob = p["line_of_business"]
        if lob == Lob.MEDSUPP:
            return is_valid_medigap_letter(p["plan_id"])
        if lob == Lob.ACA:
            return is_valid_hios_plan_id(p["plan_id"])
        return parse_medicare_plan_id(p["plan_id"]) is not None

    def off(ln: dict[str, Any], d: Defect) -> bool:
        exp = Decimal(d["injected_values"]["from"])
        return abs(ln["amount"] - exp) > max(exp / 100, Decimal(1))

    def expired(p: dict[str, Any], d: Defect) -> bool:
        return any(
            (r["npn"], r["carrier"], r["state"], r["line_of_business"])
            == (p["writing_agent_npn"], p["carrier"], p["state"], p["line_of_business"])
            and r["end_date"] is not None
            and r["end_date"] < p["effective_date"]
            for r in t["rts"]
        )

    return {
        "zip_state_mismatch": lambda c, d: not zip3_matches_state(c["zip"], c["state"]),
        "invalid_mbi": lambda c, d: not is_valid_mbi(c["mbi"]),
        "missing_mbi": lambda c, d: c["mbi"] is None and c["client_id"] in medicare_clients,
        "npn_malformed": lambda p, d: not is_valid_npn(p["writing_agent_npn"]),
        "unknown_writing_agent": lambda p, d: (
            is_valid_npn(p["writing_agent_npn"]) and p["writing_agent_npn"] not in npns
        ),
        "plan_id_malformed": lambda p, d: not plan_ok(p),
        "term_before_effective": lambda p, d: p["termination_date"] < p["effective_date"],
        "status_date_conflict": lambda p, d: (
            p["status"] == "ACTIVE" and p["termination_date"] < AS_OF
        ),
        "messy_status": lambda p, d: p["status"] not in set(PolicyStatus),
        "exact_duplicate_row": lambda p, d: (
            policy_counts[p["policy_id"]] == 2 and _rows(world, d)[0] == _rows(world, d)[1]
        ),
        "name_dob_collision": lambda c, d: (
            people[(normalize_name(f"{c['first_name']} {c['last_name']}"), c["dob"])] == 2
        ),
        "duplicate_policy_id": lambda p, d: (
            policy_counts[p["policy_id"]] == 2 and _rows(world, d)[0] != _rows(world, d)[1]
        ),
        "orphan_policy": lambda p, d: p["client_id"] not in clients,
        "orphan_commission_line": lambda ln, d: (
            ln["policy_ref"] is None and ln["carrier_member_id"] not in member_ids
        ),
        "missing_commission_line": lambda p, d: (
            p["status"] == "ACTIVE"
            and (p["policy_id"], d["injected_values"]["statement_period"]) not in paid
        ),
        "commission_off_schedule": off,
        "crm_status_conflict": lambda p, d: (
            p["status"] == "CANCELLED" and (p["policy_id"], "2026-08") in paid
        ),
        "rts_gap": lambda p, d: (
            (
                p["writing_agent_npn"],
                p["carrier"],
                p["state"],
                p["line_of_business"],
            )
            not in combos
        ),
        "rts_expired": expired,
        "license_gap": lambda p, d: (
            p["state"] not in npns[p["writing_agent_npn"]]["license_states"]
        ),
    }


def test_every_defect_is_really_in_the_world() -> None:
    world, defects = injected()
    witnesses = _witnesses(world)
    seen = Counter(d["defect_type"] for d in defects)
    assert set(seen) == set(EXPECTED)
    for d in defects:
        row = _rows(world, d)[-1]
        iv = d["injected_values"]
        if "field" in iv:
            assert str(row[iv["field"]]) == str(iv["to"]), d
        if d["defect_type"] in witnesses:
            assert witnesses[d["defect_type"]](row, d), d
    keys = [json.dumps(d["record_key"], sort_keys=True) for d in defects]
    assert len(keys) == len(set(keys))  # one defect per record, so scoring is unambiguous


def test_planted_example_3_rts_gap() -> None:
    world, defects = planted()
    t = world.tables
    p = next(p for p in t["policies"] if p["policy_id"] == PLANTED_POLICY)
    client = next(c for c in t["clients"] if c["client_id"] == p["client_id"])
    agent = next(a for a in t["agents"] if a["npn"] == PLANTED_NPN)
    assert (p["carrier"], p["state"], p["effective_date"].year) == ("Harborline", "TX", 2026)
    assert p["writing_agent_npn"] == PLANTED_NPN and p["carrier_member_id"].startswith("HL-")
    assert parse_medicare_plan_id(p["plan_id"]) is not None
    assert client["state"] == "TX" and zip3_matches_state(client["zip"], "TX")
    assert "TX" in agent["license_states"]
    assert not any(
        r["npn"] == PLANTED_NPN and r["carrier"] == "Harborline" and r["state"] == "TX"
        for r in t["rts"]
    )
    old_npns = {a["npn"] for a in clean().tables["agents"]} - {a["npn"] for a in t["agents"]}
    assert len(old_npns) == 1  # one producer renamed, everywhere
    for table in ("agents", "rts", "policies", "commission_lines"):
        assert old_npns.isdisjoint(json.dumps(t[table], default=str).split('"'))
    assert [d["defect_type"] for d in defects] == ["rts_gap", "orphan_commission_line"]
    assert defects[0]["record_key"] == {"policy_id": PLANTED_POLICY}


def test_planted_example_4_orphan_line() -> None:
    world, defects = planted()
    statement = [
        ln
        for ln in world.tables["commission_lines"]
        if (ln["carrier"], ln["statement_period"]) == ("Harborline", "2026-08")
    ]
    assert [ln["line_no"] for ln in statement] == list(range(1, len(statement) + 1))
    line = statement[211]
    assert (line["line_no"], line["amount"], line["carrier_member_id"]) == (
        212,
        Decimal("61.05"),
        "HL-998213",
    )
    assert line["policy_ref"] is None
    assert all(p["carrier_member_id"] != "HL-998213" for p in world.tables["policies"])
    assert defects[1]["record_key"] == ORPHAN_LINE


def test_planted_world_has_no_other_defects() -> None:
    """The supporting edits (renamed agent, TX license, moved policy) are not defects."""
    t = planted()[0].tables
    licenses = {a["npn"]: set(a["license_states"]) for a in t["agents"]}
    clients = {c["client_id"]: c for c in t["clients"]}
    rts = {
        (r["npn"], r["carrier"], r["state"], r["plan_year"], r["line_of_business"])
        for r in t["rts"]
    }
    paid = _paid(planted()[0])
    for p in t["policies"]:
        assert p["state"] in licenses[p["writing_agent_npn"]]
        assert p["state"] == clients[p["client_id"]]["state"]
        last = p["termination_date"] or max(p["effective_date"], AS_OF)
        for year in range(p["effective_date"].year, last.year + 1):
            key = (p["writing_agent_npn"], p["carrier"], p["state"], year, p["line_of_business"])
            assert (key in rts) == (p["policy_id"] != PLANTED_POLICY)
        for period in ("2026-06", "2026-07", "2026-08"):
            lines = paid.get((p["policy_id"], period), [])
            assert len(lines) == (1 if p["status"] == PolicyStatus.ACTIVE else 0)
            for ln in lines:
                assert ln["amount"] == expected_amount(
                    p["line_of_business"], p["effective_date"], period
                )
                assert ln["carrier"] == p["carrier"] and ln["agent_npn"] == p["writing_agent_npn"]


def test_random_injectors_never_touch_planted_records() -> None:
    (before, planted_defects), (after, defects) = planted(), injected()
    for source, key in (
        ("policies", {"policy_id": PLANTED_POLICY}),
        ("commission_lines", ORPHAN_LINE),
    ):
        d: Defect = {"source": source, "record_key": key}
        assert _rows(before, d) == _rows(after, d)
    p = _rows(before, {"source": "policies", "record_key": {"policy_id": PLANTED_POLICY}})[0]
    client = {"source": "clients", "record_key": {"client_id": p["client_id"]}}
    assert _rows(before, client) == _rows(after, client)
    assert list(defects[:2]) == list(planted_defects)
    planted_keys = [d["record_key"] for d in planted_defects] + [{"client_id": p["client_id"]}]
    assert all(d["record_key"] not in planted_keys for d in defects[2:])


def test_plant_refuses_a_world_without_the_records() -> None:
    with pytest.raises(ValueError, match="P-00417"):
        plant(build_world(seed=42, n_clients=100))


def test_injection_leaves_the_clean_world_clean() -> None:
    snapshot = copy.deepcopy(clean().tables)
    inject(clean())
    assert clean().tables == snapshot and clean().locked == frozenset()


def test_ground_truth_row_refs_and_round_trip(tmp_path: Path) -> None:
    world, defects = injected()
    write_world(world, tmp_path, list(defects), folder="canonical-defected")
    truth_path = tmp_path / "ground_truth.json"
    truth = load_ground_truth(truth_path)
    assert truth_path.read_text() == json.dumps(truth, indent=2) + "\n"
    assert truth["seed"] == 42 and len(truth["defects"]) == len(defects)
    tables: dict[str, list[dict[str, str]]] = {}
    for d in truth["defects"]:
        assert set(d) == {
            "source",
            "record_key",
            "row_ref",
            "defect_type",
            "expected_rule_ids",
            "scored",
            "injected_values",
        }
        if d["source"] not in tables:
            with (tmp_path / "canonical-defected" / f"{d['source']}.csv").open() as f:
                tables[d["source"]] = list(csv.DictReader(f))
        row = tables[d["source"]][d["row_ref"] - 2]  # row 1 is the header
        assert all(row[k] == str(v) for k, v in d["record_key"].items()), d


def test_cli_same_seed_is_byte_identical_and_matches_the_fixture(tmp_path: Path) -> None:
    for name in ("a", "b"):
        result = CliRunner().invoke(
            app, ["generate", "--seed", "42", "--out", str(tmp_path / name)]
        )
        assert result.exit_code == 0, result.output
    assert _digest(tmp_path / "a") == _digest(tmp_path / "b")
    assert sorted(_digest(tmp_path / "a")) == [
        f"canonical-defected/{t}.csv"
        for t in sorted(("agents", "clients", "commission_lines", "households", "policies", "rts"))
    ] + [
        f"drop/{f}"
        for f in sorted(
            ["agent_roster.xlsx", "crm_export.csv", "enrollment_export.csv", "manifest.json"]
            + [f"commissions_{c}.xlsx" for c in ("bluepeak", "cardinal_mutual", "harborline")]
            + [f"commissions_{c}.xlsx" for c in ("meridian_care", "northwind_health")]
            + ["commissions_summit_health_plans.xlsx"]
        )
    ] + ["ground_truth.json"]
    committed = {k: v for k, v in _digest(FIXTURE).items() if k in _digest(tmp_path / "a")}
    assert committed == _digest(tmp_path / "a"), "regenerate fixtures/agency-a (see CHANGELOG)"


def test_cli_no_inject_writes_the_clean_world(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["generate", "--seed", "3", "--clients", "60", "--no-inject", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "canonical" / "policies.csv").exists()
    assert not (tmp_path / "canonical-defected").exists()
    assert load_ground_truth(tmp_path / "ground_truth.json") == {"seed": 3, "defects": []}


def test_dates_in_ground_truth_are_strings() -> None:
    for d in injected()[1]:
        json.dumps(d["injected_values"])  # no date or Decimal objects slip through
