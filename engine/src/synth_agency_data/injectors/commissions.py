"""Commission statement defects: orphan lines, missing lines, and amounts off schedule."""

import random
from dataclasses import replace
from decimal import Decimal

from synth_agency_data.injectors.base import Defect, defect, edit, line_key, lock_key, pick
from synth_agency_data.rates import MONTHLY_RATES
from synth_agency_data.world import CARRIERS, World


def orphan_commission_line(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    """A payment for a member id no policy has, added at the end of a statement."""
    lines = list(world.tables["commission_lines"])
    used = {p["carrier_member_id"] for p in world.tables["policies"]} | {
        ln["carrier_member_id"] for ln in lines
    }
    statements = sorted({(ln["carrier"], ln["statement_period"]) for ln in lines})
    npns = sorted(a["npn"] for a in world.tables["agents"])
    defects = []
    for _ in range(max(1, round(rate * len(lines)))):
        carrier, period = rng.choice(statements)
        same = [ln for ln in lines if (ln["carrier"], ln["statement_period"]) == (carrier, period)]
        while (member := f"{CARRIERS[carrier][1]}-{rng.randint(100000, 999999)}") in used:
            pass
        used.add(member)
        amount = rng.choice(sorted(MONTHLY_RATES.values()))
        line = {
            **same[-1],
            "line_no": max(ln["line_no"] for ln in same) + 1,
            "carrier_member_id": member,
            "member_name": None,
            "member_dob": None,
            "policy_ref": None,
            "agent_npn": rng.choice(npns),
            "amount": amount,
        }
        lines.append(line)
        defects.append(
            defect(
                "orphan_commission_line",
                "commission_lines",
                line_key(line),
                "TIE-002",
                carrier_member_id=member,
                amount=amount,
            )
        )
    return replace(world, tables={**world.tables, "commission_lines": lines}), defects


def missing_commission_line(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    """Drop one period's line for a paid policy. Later lines keep their numbers (a gap)."""
    lines = world.tables["commission_lines"]
    picked = pick(
        rng,
        world,
        "commission_lines",
        rate,
        line_key,
        lambda ln: (
            ln["policy_ref"] is not None
            and lock_key({"policy_id": ln["policy_ref"]}) not in world.locked
        ),
    )
    drop: dict[str, int] = {}
    for i in picked:  # at most one missing period per policy, so the key stays unique
        drop.setdefault(lines[i]["policy_ref"], i)
    kept = [ln for i, ln in enumerate(lines) if i not in set(drop.values())]
    defects = [
        defect(
            "missing_commission_line",
            "policies",
            {"policy_id": ref},
            "TIE-001",
            statement_period=lines[i]["statement_period"],
            removed_line_no=lines[i]["line_no"],
        )
        for ref, i in sorted(drop.items())
    ]
    return replace(world, tables={**world.tables, "commission_lines": kept}), defects


def commission_off_schedule(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    """Half the scheduled amount: at least 2.10 off, beyond the 1 percent or 1 dollar tolerance."""
    rows = pick(
        rng, world, "commission_lines", rate, line_key, lambda ln: ln["policy_ref"] is not None
    )
    return edit(
        world,
        "commission_lines",
        rows,
        lambda ln: {"amount": (ln["amount"] / 2).quantize(Decimal("0.01"))},
        "commission_off_schedule",
        "TIE-003",
        line_key,
    )
