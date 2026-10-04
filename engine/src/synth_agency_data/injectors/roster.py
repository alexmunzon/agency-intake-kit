"""Roster defects: RTS rows missing or ended, and policies sold outside the agent's licenses."""

import random
from dataclasses import replace
from datetime import date
from typing import Any

from agency_schema.enums import PolicyStatus
from synth_agency_data.injectors.base import Defect, defect, edit, lock_key, pick
from synth_agency_data.world import AS_OF, Row, World

RTS_END = date(2026, 1, 31)  # an RTS row for plan year 2026 that ended in January


def _combo(row: Row, npn_field: str) -> tuple[Any, ...]:
    return (row[npn_field], row["carrier"], row["state"], row["line_of_business"])


def _clean_groups(world: World, policies: list[Row]) -> dict[tuple[Any, ...], list[Row]]:
    """Policies by (npn, carrier, state, line of business), keeping groups with no defects yet."""
    groups: dict[tuple[Any, ...], list[Row]] = {}
    for p in policies:
        groups.setdefault(_combo(p, "writing_agent_npn"), []).append(p)
    return {
        combo: ps
        for combo, ps in sorted(groups.items())
        if all(
            p["status"] in (PolicyStatus.ACTIVE, PolicyStatus.PENDING)
            and lock_key({"policy_id": p["policy_id"]}) not in world.locked
            for p in ps
        )
    }


def _take(
    rng: random.Random, groups: dict[tuple[Any, ...], list[Row]], n: int
) -> list[tuple[Any, ...]]:
    combos = list(groups)
    rng.shuffle(combos)
    taken: list[tuple[Any, ...]] = []
    while combos and sum(len(groups[c]) for c in taken) < n:
        taken.append(combos.pop())
    return taken


def rts_gap(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """Remove every RTS row for a few (agent, carrier, state, line) combinations."""
    policies = world.tables["policies"]
    groups = _clean_groups(world, policies)
    gone = set(_take(rng, groups, max(1, round(rate * len(policies)))))
    rts = [r for r in world.tables["rts"] if _combo(r, "npn") not in gone]
    defects = [
        defect(
            "rts_gap",
            "policies",
            {"policy_id": p["policy_id"]},
            "RTS-001",
            carrier=p["carrier"],
            state=p["state"],
        )
        for combo in sorted(gone)
        for p in groups[combo]
    ]
    return replace(world, tables={**world.tables, "rts": rts}), defects


def rts_expired(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """End a plan year 2026 RTS row before the start of every policy that relies on it."""
    policies = world.tables["policies"]
    in_2026 = [
        p
        for p in policies
        if p["effective_date"].year <= 2026
        and (p["termination_date"] is None or p["termination_date"].year >= 2026)
    ]
    groups = {
        c: ps
        for c, ps in _clean_groups(world, in_2026).items()
        if all(p["effective_date"] > RTS_END for p in ps)
    }
    ended = set(_take(rng, groups, max(1, round(rate * len(policies)))))
    rts = [
        {**r, "end_date": RTS_END} if r["plan_year"] == 2026 and _combo(r, "npn") in ended else r
        for r in world.tables["rts"]
    ]
    defects = [
        defect(
            "rts_expired", "policies", {"policy_id": p["policy_id"]}, "RTS-002", end_date=RTS_END
        )
        for combo in sorted(ended)
        for p in groups[combo]
    ]
    return replace(world, tables={**world.tables, "rts": rts}), defects


def license_gap(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """Sell in a state the agent is not licensed in. RTS rows are added, so only LIC-001 fires."""
    licenses = {a["npn"]: a["license_states"] for a in world.tables["agents"]}
    states = sorted({c["state"] for c in world.tables["clients"]})

    def change(p: Row) -> dict[str, str]:
        return {
            "state": rng.choice([s for s in states if s not in licenses[p["writing_agent_npn"]]])
        }

    rows = pick(
        rng, world, "policies", rate, "policy_id", lambda p: p["writing_agent_npn"] in licenses
    )
    out, defects = edit(world, "policies", rows, change, "license_gap", "LIC-001", "policy_id")
    rts = list(out.tables["rts"])
    have = {
        (r["npn"], r["carrier"], r["state"], r["plan_year"], r["line_of_business"]) for r in rts
    }
    for i in rows:
        p = out.tables["policies"][i]
        last = p["termination_date"] or max(p["effective_date"], AS_OF)
        for year in range(p["effective_date"].year, last.year + 1):
            key = (p["writing_agent_npn"], p["carrier"], p["state"], year, p["line_of_business"])
            if key not in have:
                have.add(key)
                rts.append(
                    dict(
                        zip(
                            ("npn", "carrier", "state", "plan_year", "line_of_business"),
                            key,
                            strict=True,
                        )
                    )
                    | {
                        "appointed": True,
                        "certified": True,
                        "effective_date": date(year, 1, 1),
                        "end_date": None,
                    }
                )
    return replace(out, tables={**out.tables, "rts": rts}), defects
