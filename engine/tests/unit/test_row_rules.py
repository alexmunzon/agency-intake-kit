"""One positive and one negative case per row rule (PR 8), on a single clean client and policy.

Positive values come from fixture defects where one exists (for example C-00014's MBI).
"""

from datetime import date
from typing import Any

import pytest

from agency_schema.enums import Severity
from intake.rules import ROW_FAMILIES, run_row_rules
from intake.rules.frames import client_frame, policy_frame
from intake.run.canonicalize import frame_from_rows

AS_OF = date(2026, 10, 1)
CLIENT = {
    "client_id": "C-00001",
    "first_name": "Brian",
    "last_name": "Tate",
    "dob": "1958-03-25",
    "phone": "(865) 555-0121",
    "email": "brian.tate1@example.com",
    "address_line1": "3419 Amanda Gardens",
    "city": "Lake Mark",
    "state": "GA",
    "zip": "39838",
    "mbi": "5JR1EA3UD29",
    "household_id": "H-00001",
    "notes": None,
}
POLICY = {
    "policy_id": "P-00001",
    "client_id": "C-00001",
    "carrier": "Summit Health Plans",
    "plan_id": "H5371-027-003",
    "line_of_business": "MA",
    "state": "GA",
    "eligibility_reason": "AGE",
    "effective_date": "2024-06-01",
    "termination_date": None,
    "status": "ACTIVE",
    "writing_agent_npn": "61291817",
    "monthly_premium": "9.87",
    "carrier_member_id": "SH-542828",
}
ACA = {"line_of_business": "ACA", "plan_id": "23947AL9284454", "eligibility_reason": None}
OLD = {"effective_date": "2020-01-01"}  # client is 61 then

# rule id: (positive client, positive policy), (negative client, negative policy)
CASES: dict[str, tuple[tuple[dict[str, Any], dict[str, Any]], ...]] = {
    "DOB-001": (({"dob": "1958-02-30"}, {}), ({"dob": "03/25/58"}, {})),
    "DOB-002": (({"dob": "05/01/29"}, {}), ({"dob": "1911-10-01"}, {})),
    "DOB-003": (({}, OLD), ({}, OLD | {"eligibility_reason": "DISABILITY"})),
    "MBI-001": (({"mbi": "6BX9K91AD37"}, {}), ({"mbi": "6dx9-k91-ad37"}, {})),
    "MBI-002": (({}, ACA), ({"mbi": None}, ACA)),
    "MBI-003": (({"mbi": None}, {}), ({"mbi": None}, ACA)),
    "NPN-001": (({}, {"writing_agent_npn": "18O4412"}), ({}, {"writing_agent_npn": " 61291817"})),
    "NPN-002": (({}, {"writing_agent_npn": "3798272"}), ({}, {"writing_agent_npn": "18O4412"})),
    "PLN-001": (({}, {"plan_id": "S1188013"}), ({}, {"plan_id": "h5371-027"})),
    "PLN-002": (
        ({}, ACA | {"plan_id": "76542SC946455"}),
        ({}, ACA | {"plan_id": "76542SC9464553-01"}),
    ),
    "PLN-003": (({}, {"plan_id": "S1188-013"}), ({}, {"plan_id": "R1188-013"})),
    "PLN-004": (
        ({}, {"line_of_business": "MEDSUPP", "plan_id": "H"}),
        ({}, {"line_of_business": "MEDSUPP", "plan_id": "Plan G"}),
    ),
    "ADR-001": (({"zip": "3983"}, {}), ({"zip": "39838-1234"}, {})),
    "ADR-002": (({"zip": "53439"}, {}), ({"zip": "30749"}, {})),
    "ADR-003": (({"state": "GX"}, {}), ({"state": "ga"}, {})),
    "CON-001": (({"email": "brian.tate1@example"}, {}), ({"email": " Brian.T@Example.com "}, {})),
    "CON-002": (({"phone": "555-0121"}, {}), ({"phone": "1 (865) 555-0121 ext 4"}, {})),
    "DAT-001": (({}, {"effective_date": "2024-13-01"}), ({}, {"effective_date": "45444"})),
    "DAT-002": (
        ({}, {"termination_date": "2024-05-31", "status": "TERMINATED"}),
        ({}, {"termination_date": "2024-06-01", "status": "TERMINATED"}),
    ),
    "DAT-003": (({}, {"termination_date": "2026-09-08"}), ({}, {"termination_date": "2026-12-31"})),
    "DAT-004": (
        ({}, {"effective_date": "2024-06-15"}),
        ({}, {"effective_date": "2024-06-15", "line_of_business": "MEDSUPP", "plan_id": "G"}),
    ),
    "STA-001": (({}, {"status": "chk w/ carrier"}), ({}, {"status": " pending "})),
}


def _run(client: dict[str, Any], policy: dict[str, Any]) -> list[Any]:
    clients = client_frame(frame_from_rows("clients.csv", [CLIENT | client]), AS_OF)
    agents = frame_from_rows("agents.csv", [{"npn": "61291817"}])
    policies = policy_frame(
        frame_from_rows("policies.csv", [POLICY | policy]), clients, agents, AS_OF
    )
    return run_row_rules(clients, policies)


def test_cases_cover_every_row_rule() -> None:
    from agency_schema.registry import catalog

    assert sorted(CASES) == sorted(m.rule_id for m in catalog() if m.family in ROW_FAMILIES)


def test_the_clean_base_rows_raise_nothing() -> None:
    assert _run({}, {}) == []


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_fires_on_its_defect(rule_id: str) -> None:
    client, policy = CASES[rule_id][0]
    records = [r for r in _run(client, policy) if r.rule_id == rule_id]
    assert records, f"{rule_id} did not fire"
    raw = [str(v) for v in (client | policy).values() if v and len(str(v)) > 3]
    for r in records:
        assert r.severity != Severity.BLOCKER and r.blocks_load is False
        assert not any(v in r.message for v in raw), f"raw value in {r.message!r}"


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_stays_quiet_on_the_near_miss(rule_id: str) -> None:
    client, policy = CASES[rule_id][1]
    assert rule_id not in {r.rule_id for r in _run(client, policy)}


def test_mbi_003_reports_the_client_row_once_per_medicare_policy() -> None:
    clients = client_frame(frame_from_rows("clients.csv", [CLIENT | {"mbi": None}]), AS_OF)
    agents = frame_from_rows("agents.csv", [{"npn": "61291817"}])
    two = [
        POLICY,
        POLICY | {"policy_id": "P-00002", "line_of_business": "PDP", "plan_id": "S1188-013"},
    ]
    records = run_row_rules(
        clients, policy_frame(frame_from_rows("policies.csv", two), clients, agents, AS_OF)
    )
    hits = [r for r in records if r.rule_id == "MBI-003"]
    assert [(h.source, h.row_number) for h in hits] == [("clients", 2), ("clients", 2)]
    assert len({h.id for h in hits}) == 2
    assert [h.message for h in hits] == ["No MBI on P-00001", "No MBI on P-00002"]
