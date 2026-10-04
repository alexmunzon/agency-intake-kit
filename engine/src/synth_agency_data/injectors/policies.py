"""Policy defects: agent ids, plan ids, dates, statuses, duplicates, and broken references."""

import random
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from agency_schema.enums import LineOfBusiness as Lob
from agency_schema.enums import PolicyStatus
from synth_agency_data.injectors.base import Defect, defect, edit, pick
from synth_agency_data.world import AS_OF, Row, World

MESSY_STATUSES = ("See notes", "XFER", "??", "chk w/ carrier", "N/A")
PLAN_RULES = {Lob.MA: "PLN-001", Lob.PDP: "PLN-001", Lob.ACA: "PLN-002", Lob.MEDSUPP: "PLN-004"}


def npn_malformed(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "policies", rate, "policy_id")
    return edit(
        world,
        "policies",
        rows,
        lambda p: {
            "writing_agent_npn": p["writing_agent_npn"][:2] + "O" + p["writing_agent_npn"][3:]
        },
        "npn_malformed",
        "NPN-001",
        "policy_id",
    )


def unknown_writing_agent(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    roster = {a["npn"] for a in world.tables["agents"]}

    def change(p: Row) -> dict[str, str]:
        while (npn := str(rng.randint(1_000_000, 99_999_999))) in roster:
            pass
        return {"writing_agent_npn": npn}

    rows = pick(rng, world, "policies", rate, "policy_id")
    return edit(world, "policies", rows, change, "unknown_writing_agent", "NPN-002", "policy_id")


def _break_plan(plan_id: str, lob: str, rng: random.Random) -> str:
    if lob == Lob.MEDSUPP:
        return rng.choice("EHIJ")  # not a Medigap plan letter
    if lob == Lob.ACA:
        return plan_id[:-1]  # 13 characters
    return plan_id.replace("-", "", 1)  # H1234001


def plan_id_malformed(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "policies", rate, "policy_id")
    out, defects = edit(
        world,
        "policies",
        rows,
        lambda p: {"plan_id": _break_plan(p["plan_id"], p["line_of_business"], rng)},
        "plan_id_malformed",
        "PLN-001",
        "policy_id",
    )
    for i, d in zip(rows, defects, strict=True):  # the rule depends on the line of business
        d["expected_rule_ids"] = [PLAN_RULES[world.tables["policies"][i]["line_of_business"]]]
    return out, defects


def term_before_effective(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    rows = pick(
        rng, world, "policies", rate, "policy_id", lambda p: p["status"] == PolicyStatus.TERMINATED
    )
    return edit(
        world,
        "policies",
        rows,
        lambda p: {"termination_date": p["effective_date"] - timedelta(days=rng.randint(1, 90))},
        "term_before_effective",
        "DAT-002",
        "policy_id",
    )


def status_date_conflict(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    """ACTIVE, but a termination date already passed. The carrier still pays it."""
    rows = pick(
        rng,
        world,
        "policies",
        rate,
        "policy_id",
        lambda p: (
            p["status"] == PolicyStatus.ACTIVE and p["effective_date"] < AS_OF - timedelta(days=60)
        ),
    )
    return edit(
        world,
        "policies",
        rows,
        lambda p: {"termination_date": AS_OF - timedelta(days=rng.randint(1, 30))},
        "status_date_conflict",
        "DAT-003",
        "policy_id",
    )


def messy_status(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """Unrecognizable status words, only on unpaid policies so tie-out leg C stays quiet."""
    rows = pick(
        rng, world, "policies", rate, "policy_id", lambda p: p["status"] != PolicyStatus.ACTIVE
    )
    return edit(
        world,
        "policies",
        rows,
        lambda p: {"status": rng.choice(MESSY_STATUSES)},
        "messy_status",
        "STA-001",
        "policy_id",
    )


def _duplicate(
    world: World, rng: random.Random, rate: float, name: str, rule_id: str
) -> tuple[World, list[Defect]]:
    """Insert a second row for a policy right after the first (an exact copy, or a changed one)."""
    policies = list(world.tables["policies"])
    defects = []
    for i in reversed(pick(rng, world, "policies", rate, "policy_id")):
        copy = dict(policies[i])
        if rule_id == "DUP-003":
            copy["monthly_premium"] = (copy["monthly_premium"] + Decimal("12.00")).quantize(
                Decimal("0.01")
            )
        policies.insert(i + 1, copy)
        defects.append(
            defect(
                name,
                "policies",
                {"policy_id": copy["policy_id"]},
                rule_id,
                monthly_premium=copy["monthly_premium"],
            )
        )
    return replace(world, tables={**world.tables, "policies": policies}), defects[::-1]


def exact_duplicate_row(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    return _duplicate(world, rng, rate, "exact_duplicate_row", "DUP-001")


def duplicate_policy_id(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    return _duplicate(world, rng, rate, "duplicate_policy_id", "DUP-003")


def orphan_policy(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "policies", rate, "policy_id")
    return edit(
        world,
        "policies",
        rows,
        lambda p: {"client_id": f"C-9{rng.randrange(10_000):04d}"},  # above any real client id
        "orphan_policy",
        "REF-001",
        "policy_id",
    )


def crm_status_conflict(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    """The CRM says CANCELLED while the carrier keeps paying."""
    rows = pick(
        rng, world, "policies", rate, "policy_id", lambda p: p["status"] == PolicyStatus.ACTIVE
    )
    return edit(
        world,
        "policies",
        rows,
        lambda p: {"status": PolicyStatus.CANCELLED},
        "crm_status_conflict",
        "TIE-004",
        "policy_id",
    )
