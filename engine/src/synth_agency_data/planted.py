"""The named records from SPEC examples 3 and 4, planted on top of the seed-42 world.

Example 3: P-00417 is a Harborline MA policy in TX for plan year 2026, written by NPN 1884412,
with no RTS row for that combination (RTS-001). To get there, one producer is renamed to
1884412 everywhere, gets a TX license (so no license gap fires), and the policy moves to an
existing TX client. Example 4: Harborline 2026-08 line 212 pays 61.05 for HL-998213, a member
id no policy has (TIE-002). It is inserted, so the lines after it shift down by one.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from agency_schema.enums import EligibilityReason, PolicyStatus
from agency_schema.enums import LineOfBusiness as Lob
from synth_agency_data.injectors.base import Defect, defect, lock_key
from synth_agency_data.world import Row, World, commission_lines

PLANTED_POLICY = "P-00417"
PLANTED_NPN = "1884412"
ORPHAN_LINE: dict[str, Any] = {
    "carrier": "Harborline",
    "statement_period": "2026-08",
    "line_no": 212,
}
ORPHAN_MEMBER = "HL-998213"
ORPHAN_AMOUNT = Decimal("61.05")


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def plant(world: World) -> tuple[World, list[Defect]]:
    t = world.tables
    policies = list(t["policies"])
    at = next((i for i, p in enumerate(policies) if p["policy_id"] == PLANTED_POLICY), None)
    if at is None or policies[at]["line_of_business"] != Lob.MA:
        raise ValueError(f"planted records need {PLANTED_POLICY} as an MA policy (use seed 42)")
    start = policies[at]["effective_date"]
    held: dict[str, set[str]] = {}
    for p in policies:
        held.setdefault(p["client_id"], set()).add(p["line_of_business"])
    client = next(
        (
            c
            for c in t["clients"]
            if c["state"] == "TX"
            and c["mbi"]
            and _age(c["dob"], start) >= 65
            and held[c["client_id"]] == {Lob.PDP}
        ),
        None,
    )
    hl_tx = {
        p["writing_agent_npn"]
        for p in policies
        if (p["carrier"], p["state"]) == ("Harborline", "TX")
    }
    agent = next((a for a in t["agents"][5:] if a["npn"] not in hl_tx), None)
    npns = {a["npn"] for a in t["agents"]}
    members = {p["carrier_member_id"] for p in policies}
    if client is None or agent is None or PLANTED_NPN in npns or ORPHAN_MEMBER in members:
        raise ValueError("this world cannot hold the planted records (use seed 42)")

    old = agent["npn"]

    def rename(npn: str | None) -> str | None:
        return PLANTED_NPN if npn == old else npn

    agents = [
        {
            **a,
            "npn": rename(a["npn"]),
            "upline_npn": rename(a["upline_npn"]),
            "license_states": tuple(sorted({*a["license_states"], "TX"}))
            if a is agent
            else a["license_states"],
        }
        for a in t["agents"]
    ]
    rts = [{**r, "npn": rename(r["npn"])} for r in t["rts"]]
    policies = [{**p, "writing_agent_npn": rename(p["writing_agent_npn"])} for p in policies]
    member = next(f"HL-{n}" for n in range(100417, 1_000_000) if f"HL-{n}" not in members)
    policies[at] = {
        **policies[at],
        "client_id": client["client_id"],
        "carrier": "Harborline",
        "plan_id": next(
            p["plan_id"]
            for p in policies
            if (p["carrier"], p["line_of_business"]) == ("Harborline", Lob.MA)
        ),
        "state": "TX",
        "eligibility_reason": EligibilityReason.AGE,
        "status": PolicyStatus.ACTIVE,
        "writing_agent_npn": PLANTED_NPN,
        "carrier_member_id": member,
    }

    lines = commission_lines(policies, t["clients"])
    statement = [
        i
        for i, ln in enumerate(lines)
        if (ln["carrier"], ln["statement_period"]) == ("Harborline", "2026-08")
    ]
    if len(statement) < ORPHAN_LINE["line_no"]:
        raise ValueError("the Harborline 2026-08 statement is too short for line 212 (use seed 42)")
    pos = statement[ORPHAN_LINE["line_no"] - 1]
    for i in statement[ORPHAN_LINE["line_no"] - 1 :]:
        lines[i] = {**lines[i], "line_no": lines[i]["line_no"] + 1}
    orphan: Row = {
        **lines[pos],
        **ORPHAN_LINE,
        "carrier_member_id": ORPHAN_MEMBER,
        "member_name": None,
        "member_dob": None,
        "policy_ref": None,
        "agent_npn": None,
        "amount": ORPHAN_AMOUNT,
    }
    lines.insert(pos, orphan)

    keys = [{"policy_id": PLANTED_POLICY}, ORPHAN_LINE, {"client_id": client["client_id"]}]
    defects = [
        defect(
            "rts_gap",
            "policies",
            {"policy_id": PLANTED_POLICY},
            "RTS-001",
            planted="SPEC example 3",
            npn=PLANTED_NPN,
            carrier="Harborline",
            state="TX",
            plan_year=2026,
        ),
        defect(
            "orphan_commission_line",
            "commission_lines",
            dict(ORPHAN_LINE),
            "TIE-002",
            planted="SPEC example 4",
            carrier_member_id=ORPHAN_MEMBER,
            amount=ORPHAN_AMOUNT,
        ),
    ]
    tables = {**t, "agents": agents, "rts": rts, "policies": policies, "commission_lines": lines}
    return replace(world, tables=tables, locked=world.locked | {lock_key(k) for k in keys}), defects
