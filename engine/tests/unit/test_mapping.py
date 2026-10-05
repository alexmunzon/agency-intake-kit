"""PR 5: synonym mapping, the mapping store, MAP-001, and MAP-003."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agency_schema.enums import Severity
from intake.ingest import IngestResult, ingest
from intake.mapping.headers import map_headers, map_table, mapping_key
from intake.mapping.store import (
    MappingEntry,
    SourceMapping,
    dump_mapping,
    load_mapping,
    mapping_path,
    parse_mapping,
    save_mapping,
)
from intake.mapping.synonyms import SynonymTable, Target, load_synonyms, normalize_header

FIXTURES = Path(__file__).parents[3] / "fixtures"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)

CRM = {
    "Client ID": "clients.client_id",
    "Client Name": "clients.full_name",
    "Mbr DOB": "clients.dob",
    "Primary Phone": "clients.phone",
    "Email": "clients.email",
    "Address": "clients.address_line1",
    "City": "clients.city",
    "State": "clients.state",
    "Zip": "clients.zip",
    "Medicare ID": "clients.mbi",
    "Household": "clients.household_id",
    "Policy #": "policies.policy_id",
    "Carrier Name": "policies.carrier",
    "Plan": "policies.plan_id",
    "Product": "policies.line_of_business",
    "Policy State": "policies.state",
    "Eligibility": "policies.eligibility_reason",
    "Member ID": "policies.carrier_member_id",
    "Eff Date": "policies.effective_date",
    "Term Date": "policies.termination_date",
    "Status": "policies.status",
    "Writing Agent NPN": "policies.writing_agent_npn",
    "Premium": "policies.monthly_premium",
    "Notes": "clients.notes",
}
ENROLLMENT = {
    "member_first": "clients.first_name",
    "member_last": "clients.last_name",
    "Birth Dt (mm/dd/yy)": None,  # SPEC example 2: Jev maps it in PR 7
    "mbi": "clients.mbi",
    "carrier": "policies.carrier",
    "contract_plan": "policies.plan_id",
    "effective": "policies.effective_date",
    "agent_npn": "policies.writing_agent_npn",
    "application_status": "policies.status",
    "policy_number": "policies.policy_id",
}
STATEMENT_LINE = {
    "Line": "line_no",
    "Period": "statement_period",
    "Member ID": "carrier_member_id",
    "Member Name": "member_name",
    "DOB": "member_dob",
    "Policy": "policy_ref",
    "Writing Agent": "agent_npn",
    "Type": "commission_type",
    "Paid": None,  # a date or an amount; the values decide, so Jev does (PR 7)
    "Commission": "amount",
}
STATEMENT_STMT = {
    "Stmt Period": "statement_period",
    "Seq #": "line_no",
    "Subscriber Name": "member_name",
    "Subscriber ID": "carrier_member_id",
    "Birth Date": "member_dob",
    "Agent NPN": "agent_npn",
    "Agency Policy Ref": "policy_ref",
    "Txn Type": "commission_type",
    "Pay Date": "paid_date",
    "Amount Paid": "amount",
}
STATEMENT_MONTH = {
    "Statement Month": "statement_period",
    "Line No": "line_no",
    "Member #": "carrier_member_id",
    "Insured": "member_name",
    "Date of Birth": "member_dob",
    "Producer NPN": "agent_npn",
    "Ref": "policy_ref",
    "Comm Type": "commission_type",
    "Payment Date": "paid_date",
    "Comp $": "amount",
}
AGENTS = {
    "Agent Name": "full_name",
    "NPN #": "npn",
    "E-mail": "email",
    "Licensed States": "license_states",
    "Upline NPN": "upline_npn",
    "Status": "status",
}
RTS = {
    "NPN": "npn",
    "Carrier": "carrier",
    "State": "state",
    "Plan Yr": "plan_year",
    "Line": "line_of_business",
    "Appointed?": "appointed",
    "Certified?": "certified",
    "RTS Start": "effective_date",
    "RTS End": "end_date",
}


def _qualify(table: str, fields: dict[str, str | None]) -> dict[str, str | None]:
    return {h: f"{table}.{f}" if f else None for h, f in fields.items()}


EXPECTED: dict[str, dict[str, str | None]] = {
    "crm": CRM,
    "enrollment": ENROLLMENT,
    "statement_northwind_health": _qualify("commission_lines", STATEMENT_LINE),
    "statement_cardinal_mutual": _qualify("commission_lines", STATEMENT_LINE),
    "statement_bluepeak": _qualify("commission_lines", STATEMENT_STMT),
    "statement_summit_health_plans": _qualify("commission_lines", STATEMENT_STMT),
    "statement_harborline": _qualify("commission_lines", STATEMENT_MONTH),
    "statement_meridian_care": _qualify("commission_lines", STATEMENT_MONTH),
    "roster_agents": _qualify("agents", AGENTS),
    "roster_rts": _qualify("rts", RTS),
}


@pytest.fixture(scope="module")
def agency_a() -> IngestResult:
    return ingest(FIXTURES / "agency-a" / "drop", run_id="test-run")


def _targets(mapping: SourceMapping) -> dict[str, str | None]:
    return {e.header: f"{e.table}.{e.field}" if e.field else None for e in mapping.entries}


def test_every_fixture_header_maps_to_its_canonical_field(
    agency_a: IngestResult, tmp_path: Path
) -> None:
    seen = {}
    for table in agency_a.tables:
        result = map_table(table, tmp_path, NOW)
        seen[mapping_key(table.source, table.sheet)] = _targets(result.mapping)
    assert seen == EXPECTED


def test_agency_a_warns_only_for_headers_left_to_jev_and_never_blocks(
    agency_a: IngestResult, tmp_path: Path
) -> None:
    records = [r for t in agency_a.tables for r in map_table(t, tmp_path, NOW).exceptions]
    assert sorted((r.rule_id, r.source) for r in records) == [
        ("MAP-001", "enrollment"),
        ("MAP-001", "statement_cardinal_mutual"),
        ("MAP-001", "statement_northwind_health"),
    ]
    assert not any(r.blocks_load for r in records)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f"{k}.yaml" for k in EXPECTED)


def test_unknown_header_stays_unmapped_and_map_001_lists_candidates(tmp_path: Path) -> None:
    result = map_headers("crm", None, [*CRM, "Birth Dt (mm/dd/yy)", "Zodiac"], tmp_path, NOW)
    assert _targets(result.mapping)["Zodiac"] is None
    by_header = {r.message.split('"')[1]: r for r in result.exceptions}
    assert set(by_header) == {"Birth Dt (mm/dd/yy)", "Zodiac"}
    dob = by_header["Birth Dt (mm/dd/yy)"]
    assert dob.severity == Severity.WARNING and not dob.blocks_load
    assert dob.suggested_fix is not None and "clients.dob" in dob.suggested_fix
    assert "mapping/crm.yaml" in dob.suggested_fix
    assert "Closest fields: none" in (by_header["Zodiac"].suggested_fix or "")


@pytest.mark.parametrize("header", ["Eff Dates", "Mbr DOB 2", "Client", "Policy State Code"])
def test_a_near_match_is_offered_but_never_mapped(header: str) -> None:
    match = load_synonyms().match(header, ("clients", "policies"))
    assert match.target is None
    assert match.candidates


def test_normalize_handles_case_spacing_punctuation_and_abbreviations() -> None:
    assert normalize_header("  Mbr   DOB ") == "member dob"
    assert normalize_header("Policy #") == normalize_header("policy_number") == "policy number"
    assert normalize_header("Eff. Date") == normalize_header("effective-date")
    assert normalize_header("PlanYr") == "plan year"
    assert normalize_header("Appointed?") == "appointed"
    assert normalize_header("Año") == "ano"


@given(st.text())
def test_normalization_is_idempotent(header: str) -> None:
    once = normalize_header(header)
    assert normalize_header(once) == once


def test_a_spelling_meaning_two_fields_of_one_table_is_refused() -> None:
    with pytest.raises(ValueError, match="two fields"):
        SynonymTable({"clients": {"city": ["Town"], "state": ["town"]}})
    with pytest.raises(ValueError, match="no field"):
        SynonymTable({"clients": {"zodiac": ["sign"]}})


def _mapping() -> SourceMapping:
    stamp = NOW.isoformat()
    return SourceMapping(
        source="crm",
        entries=(
            MappingEntry(header="Policy #", table="policies", field="policy_id",
                         method="synonym", confidence=1.0, decided_at=stamp),
            MappingEntry(header="Birth Dt (mm/dd/yy)", table=None, field=None,
                         method="unmapped", confidence=None, decided_at=stamp),
            MappingEntry(header="Comp $: Año", table="clients", field="dob",
                         method="jev", confidence=0.91, decided_at=stamp),
            MappingEntry(header="Notes", table=None, field=None,
                         method="manual", confidence=None, decided_at=stamp),
        ),
    )  # fmt: skip


def test_store_round_trips_byte_for_byte(tmp_path: Path) -> None:
    path = save_mapping(tmp_path, _mapping())
    data = path.read_bytes()
    assert parse_mapping(data.decode()) == _mapping()
    assert dump_mapping(parse_mapping(data.decode())).encode() == data
    assert load_mapping(tmp_path, "crm") == _mapping()
    assert load_mapping(tmp_path, "enrollment") is None


def test_store_refuses_entries_that_do_not_add_up() -> None:
    with pytest.raises(ValueError, match="needs a field"):
        MappingEntry(header="X", table=None, field=None, method="synonym",
                     confidence=1.0, decided_at="t")  # fmt: skip
    with pytest.raises(ValueError, match="no field"):
        MappingEntry(header="X", table="clients", field="dob", method="unmapped",
                     confidence=None, decided_at="t")  # fmt: skip


def test_second_run_reuses_the_stored_mapping_unchanged(tmp_path: Path) -> None:
    first = map_headers("crm", None, list(CRM), tmp_path, NOW)
    data = mapping_path(tmp_path, "crm").read_bytes()
    second = map_headers("crm", None, list(CRM), tmp_path, LATER)
    assert mapping_path(tmp_path, "crm").read_bytes() == data
    assert second.mapping == first.mapping and second.version == first.version


def test_a_stored_decision_wins_over_the_synonym_table(tmp_path: Path) -> None:
    headers = list(STATEMENT_LINE)
    map_headers("statement_cardinal_mutual", "Statement", headers, tmp_path, NOW)
    path = mapping_path(tmp_path, "statement_cardinal_mutual")
    text = path.read_text()
    paid = "- header: Paid\n  table: null\n  field: null\n  method: unmapped"
    assert paid in text
    path.write_text(
        text.replace(paid, "- header: Paid\n  table: commission_lines\n  field: paid_date\n"
                     "  method: manual")
    )  # fmt: skip
    result = map_headers("statement_cardinal_mutual", "Statement", headers, tmp_path, LATER)
    assert _targets(result.mapping)["Paid"] == "commission_lines.paid_date"
    assert result.exceptions == []
    # A person ignoring a column silences MAP-001 for it.
    ignored = map_headers("crm", None, ["Zodiac"], tmp_path, NOW).mapping
    save_mapping(tmp_path, ignored.model_copy(update={"entries": (
        ignored.entries[0].model_copy(update={"method": "manual"}),)}))  # fmt: skip
    again = map_headers("crm", None, ["Zodiac"], tmp_path, NOW)
    assert [r.rule_id for r in again.exceptions] == ["MAP-003"] * 15


def test_a_stored_mapping_to_an_unknown_field_is_refused(tmp_path: Path) -> None:
    bad = _mapping().model_copy(update={"entries": (
        MappingEntry(header="Policy #", table="policies", field="zodiac",
                     method="manual", confidence=None, decided_at="t"),)})  # fmt: skip
    save_mapping(tmp_path, bad)
    with pytest.raises(ValueError, match="policies.zodiac"):
        map_headers("crm", None, ["Policy #"], tmp_path, NOW)


def test_map_003_blocks_when_a_required_field_has_no_column(tmp_path: Path) -> None:
    headers = [h for h in CRM if h not in ("Mbr DOB", "Client Name")]
    records = map_headers("crm", None, headers, tmp_path, NOW).exceptions
    assert sorted(r.field or "" for r in records) == ["dob", "first_name", "last_name"]
    for record in records:
        assert record.rule_id == "MAP-003" and record.severity == Severity.BLOCKER
        assert record.blocks_load is True and record.source == "crm"
        assert record.lineage is None and "crm is missing" in record.message


def test_the_same_field_from_two_columns_maps_only_the_first(tmp_path: Path) -> None:
    result = map_headers("roster", "Agents", [*AGENTS, "Email"], tmp_path, NOW)
    assert _targets(result.mapping)["Email"] is None
    (record,) = result.exceptions
    assert record.rule_id == "MAP-001" and "agents.email" in (record.suggested_fix or "")


def test_an_ssn_shaped_header_is_masked_in_the_message(tmp_path: Path) -> None:
    result = map_headers("roster", "Agents", [*AGENTS, "123-45-6789"], tmp_path, NOW)
    (record,) = result.exceptions
    assert "123-45-6789" not in record.message and "12" in record.message


def test_targets_print_as_table_dot_field() -> None:
    assert str(Target("clients", "dob")) == "clients.dob"
