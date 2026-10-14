"""REF-002: a policy filed under the wrong client.

A policy filed under client A is flagged when carrier statement lines that matched it by BOTH
member ID and policy number name exactly one other existing client B. Links come from the real
tie-out, so the ambiguous conflicting_name_dob state the matcher gives a misfiled line is the
one exercised here, not a hand-written stand-in.
"""

import random
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

import intake.rules.catalog  # noqa: F401  (registers REF-002, which runs outside the registry)
from agency_schema.enums import Family, Severity
from agency_schema.outputs import JevMode
from agency_schema.registry import catalog
from intake.checks.references import misfiled_policies
from intake.exceptions.policy import excluded_rows
from intake.readers import build_frame
from intake.run.pipeline import RunOptions, run
from intake.tieout import run_tieout
from synth_agency_data.canonical_writer import write_ground_truth
from synth_agency_data.injectors import INJECTORS, Defect, lock_key
from synth_agency_data.injectors.commissions import total_variances
from synth_agency_data.injectors.policies import misfiled_policy
from synth_agency_data.world import build_world
from synth_agency_data.writers import write_drop

RATES = {("MA", "NEW"): Decimal("52.50"), ("MA", "RENEWAL"): Decimal("26.25")}
POLICY = "policy_id client_id carrier carrier_member_id line_of_business effective_date "
POLICY += "termination_date status writing_agent_npn"
LINE = "carrier statement_period line_no carrier_member_id member_name member_dob policy_ref "
LINE += "agent_npn amount commission_type"
CLIENT = "client_id first_name last_name dob"
Cells = list[str | None]

EMILY = ["C-1", "Emily", "Morris", "1950-01-02"]
PAULA = ["C-456", "Paula", "Murray", "1953-04-02"]


def frame(header: str, rows: list[Cells], file: str, sheet: str | None = None,
          first_row: int = 2) -> pl.DataFrame:  # fmt: skip
    return build_frame(
        header.split(),
        [(first_row + i, r) for i, r in enumerate(rows)],
        source_file=file,
        sheet=sheet,
        run_id="run-7",
        mapping_version="v2",
    )


def policy(pid: str, client: str = "C-1", carrier: str = "Bluepeak") -> Cells:
    return [pid, client, carrier, f"M-{pid}", "MA", "2020-01-01", None, "ACTIVE", "1234567"]


def line(no: int, pid: str, name: str = "Paula Murray", dob: str = "1953-04-02",
         period: str = "2026-06", ref: str | None = "same",
         carrier: str = "Bluepeak") -> Cells:  # fmt: skip
    policy_ref = pid if ref == "same" else ref
    return [carrier, period, str(no), f"M-{pid}", name, dob, policy_ref, "1234567", "26.25",
            "RENEWAL"]  # fmt: skip


def check(policies: list[Cells], lines: list[Cells], clients: list[Cells]):
    tables = {
        "policies": frame(POLICY, policies, "crm.csv"),
        "commission_lines": frame(LINE, lines, "bluepeak.xlsx", "Statement", 4),
        "clients": frame(CLIENT, clients, "crm_clients.csv"),
    }
    tie = run_tieout(tables, run_id="run-7", rates=RATES)
    return tie, misfiled_policies(tables, tie.links)


def test_fires_when_lines_held_ambiguous_name_another_real_client() -> None:
    # Paula has her own Bluepeak policy, so name/DOB points the line at P-2 and the matcher
    # holds it as ambiguous conflicting_name_dob. REF-002 must still read it.
    tie, found = check(
        [policy("P-123"), policy("P-2", "C-456")], [line(1, "P-123")], [EMILY, PAULA]
    )
    assert (tie.links[0].state, tie.links[0].reason) == ("ambiguous", "conflicting_name_dob")
    assert [r.rule_id for r in found] == ["REF-002"]
    record = found[0]
    assert record.severity == Severity.ERROR
    assert record.source == "policies"
    assert record.row_number == 2  # P-123's own CRM row
    assert record.lineage is not None and record.lineage.source_file == "crm.csv"
    assert "P-123" in record.message and "C-1" in record.message and "C-456" in record.message
    assert "Paula" not in record.message and "1953" not in record.message  # IDs only
    assert record.suggested_fix


def test_fires_when_lines_are_confirmed() -> None:
    tie, found = check([policy("P-123")], [line(1, "P-123")], [EMILY, PAULA])
    assert tie.links[0].state == "confirmed"
    assert [r.rule_id for r in found] == ["REF-002"]


def test_silent_when_lines_name_the_filed_client() -> None:
    _, found = check(
        [policy("P-123")], [line(1, "P-123", "Emily Morris", "1950-01-02")], [EMILY, PAULA]
    )
    assert found == []


def test_silent_on_typo_or_nickname_that_matches_nobody() -> None:
    lines = [line(1, "P-123", "Paula Murrey"), line(2, "P-123", "Polly Murray")]
    _, found = check([policy("P-123")], lines, [EMILY, PAULA])
    assert found == []


def test_silent_when_two_other_clients_share_the_name_and_dob() -> None:
    twin = ["C-789", "Paula", "Murray", "1953-04-02"]
    _, found = check([policy("P-123")], [line(1, "P-123")], [EMILY, PAULA, twin])
    assert found == []


def test_silent_when_only_one_strong_key_matched() -> None:
    _, found = check([policy("P-123")], [line(1, "P-123", ref=None)], [EMILY, PAULA])
    assert found == []


def test_silent_for_an_orphan_policy() -> None:
    _, found = check([policy("P-123", "C-9")], [line(1, "P-123")], [EMILY, PAULA])
    assert found == []


def test_silent_when_the_filed_client_has_no_readable_name_or_dob() -> None:
    _, found = check([policy("P-123")], [line(1, "P-123")], [["C-1", "", "", None], PAULA])
    assert found == []


def test_one_exception_per_policy_across_three_periods() -> None:
    lines = [line(i, "P-123", period=f"2026-0{5 + i}") for i in (1, 2, 3)]
    _, found = check([policy("P-123")], lines, [EMILY, PAULA])
    assert len(found) == 1
    assert "3 carrier statement lines" in found[0].message


def test_silent_when_lines_name_different_other_clients() -> None:
    other = ["C-789", "Rosa", "Diaz", "1949-07-08"]
    lines = [line(1, "P-123"), line(2, "P-123", "Rosa Diaz", "1949-07-08", "2026-07")]
    _, found = check([policy("P-123")], lines, [EMILY, PAULA, other])
    assert found == []


def test_silent_when_some_lines_name_the_filed_client() -> None:
    lines = [line(1, "P-123"), line(2, "P-123", "Emily Morris", "1950-01-02", "2026-07")]
    _, found = check([policy("P-123")], lines, [EMILY, PAULA])
    assert found == []


def test_error_keeps_the_policy_row_out_of_clean() -> None:
    _, found = check([policy("P-123")], [line(1, "P-123")], [EMILY, PAULA])
    assert ("policies", 2) in excluded_rows(found)
    assert not any(r.blocks_load for r in found)


def test_registered_as_a_ref_error_that_never_blocks() -> None:
    meta = {m.rule_id: m for m in catalog()}["REF-002"]
    assert (meta.severity, meta.family, meta.blocks) == (Severity.ERROR, Family.REF, False)


def test_exact_duplicate_crm_row_of_a_misfiled_policy_is_flagged_too() -> None:
    # The tie-out links only the first copy of a (carrier, policy) in the book, so the DUP-001
    # copy would otherwise reach clean/ still filed under the wrong client.
    _, found = check([policy("P-123"), policy("P-123")], [line(1, "P-123")], [EMILY, PAULA])
    assert [(r.rule_id, r.row_number) for r in found] == [("REF-002", 2), ("REF-002", 3)]
    assert {("policies", 2), ("policies", 3)} <= excluded_rows(found)
    assert len({r.id for r in found}) == 2


def test_household_hint_when_both_clients_share_a_last_name() -> None:
    spouse = ["C-456", "Paul", "Morris", "1951-03-04"]
    _, found = check([policy("P-123")], [line(1, "P-123", "Paul Morris", "1951-03-04")],
                     [EMILY, spouse])  # fmt: skip
    assert len(found) == 1
    assert "share a last name" in found[0].message
    assert "household member" in found[0].message
    assert "Paul" not in found[0].message and "Morris" not in found[0].message


def test_no_household_hint_for_different_last_names() -> None:
    _, found = check([policy("P-123")], [line(1, "P-123")], [EMILY, PAULA])
    assert "share a last name" not in found[0].message


def test_line_naming_filed_client_with_unreadable_dob_does_not_veto() -> None:
    # Intended: a line whose DOB does not read names no one, so it neither supports nor
    # contradicts the other lines. Only readable name and DOB evidence counts.
    lines = [line(1, "P-123"), line(2, "P-123", "Emily Morris", "not a date", "2026-07")]
    _, found = check([policy("P-123")], lines, [EMILY, PAULA])
    assert [r.rule_id for r in found] == ["REF-002"]
    assert "1 carrier statement line " in found[0].message


def test_same_policy_id_at_two_carriers_is_judged_per_carrier() -> None:
    policies = [policy("P-123"), policy("P-123", carrier="Harborline")]
    lines = [
        line(1, "P-123"),
        line(2, "P-123", "Emily Morris", "1950-01-02", carrier="Harborline"),
    ]
    _, found = check(policies, lines, [EMILY, PAULA])
    assert [(r.rule_id, r.row_number) for r in found] == [("REF-002", 2)]


def test_recall_on_a_small_injected_world(tmp_path: Path) -> None:
    """End to end: plant misfiled policies, write the drop, run the real pipeline (Jev off)."""
    # inject() without planted.plant(), which needs the full-size world, as the scale tests do.
    world = build_world(seed=42, n_clients=200)
    rng = random.Random(f"inject-{world.seed}")
    defects: list[Defect] = []
    for fn, rate in [*INJECTORS, (misfiled_policy, 0.02)]:
        world, new = fn(world, rng, rate)
        world = replace(world, locked=world.locked | {lock_key(d["record_key"]) for d in new})
        defects += new
    moved = [d for d in defects if d["defect_type"] == "misfiled_policy"]
    assert moved
    located = write_drop(world, defects + total_variances(world), tmp_path / "w" / "drop")
    write_ground_truth(world, tmp_path / "w", located)
    result = run(
        RunOptions(
            drop=tmp_path / "w" / "drop",
            out=tmp_path / "run",
            jev_mode=JevMode.OFF,
            as_of=datetime(2026, 10, 1, 9, tzinfo=UTC),
        )
    )
    assert result.score is not None
    cls = {c.defect_class: c for c in result.score.summary.classes}["misfiled_policy"]
    assert cls.planted == cls.detected == len(moved) > 0
    assert result.score.false_positives_by_rule.get("REF-002", 0) == 0
    # The misfile is the only inconsistency it adds: no knock-on flags on clean rows, and it
    # hides no other planted defect.
    assert result.score.summary.false_positive_rows == 0, result.score.false_positives_by_rule
    missed = {
        c.defect_class: (c.planted, c.detected)
        for c in result.score.summary.classes
        if c.scored and c.planted != c.detected
    }
    assert not missed, (missed, result.score.missed)
