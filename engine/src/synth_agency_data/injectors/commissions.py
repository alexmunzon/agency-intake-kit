"""Commission statement defects: orphan lines, missing lines, amounts off schedule, and the
carrier and agent totals those push past tolerance."""

import random
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from agency_schema.enums import PolicyStatus
from synth_agency_data.injectors.base import Defect, defect, edit, line_key, lock_key, pick
from synth_agency_data.rates import MONTHLY_RATES, expected_amount
from synth_agency_data.world import CARRIERS, Row, World

ZERO = Decimal("0.00")
# SPEC: carrier and agent totals tie within 0.5 percent (intake.config.TIE_TOTAL_TOLERANCE_PCT).
# Repeated here because the synth package describes fake data and never imports the pipeline.
TOTAL_TOLERANCE = Decimal("0.005")


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


def _due_months(p: Row, periods: list[str]) -> list[str]:
    """Statement periods a policy is in force for (effective by month end, not ended before)."""
    due = []
    for period in periods:
        year, month = (int(x) for x in period.split("-"))
        start = date(year, month, 1)
        end = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        term = p["termination_date"]
        if p["effective_date"] <= end and (term is None or term >= start):
            due.append(period)
    return due


def _agent(npn: str | None) -> str:
    return (npn or "").strip() or "(blank)"


def total_variances(world: World) -> list[Defect]:
    """TIE-005 by carrier and by agent: a consequence of the line injectors, not an injector.

    Missing lines, half-paid lines, and orphan payments (including SPEC example 4) together move
    every carrier's statement total, and most agents' totals, more than 0.5 percent away from
    what the book expects. Tie-out correctly flags those totals, so ground truth must expect
    them. Computed from the injected amounts the way SPEC defines the totals: the book side is
    each ACTIVE policy (first row per policy id) at its scheduled rate for every period its
    carrier sent a statement, grouped by the writing agent; the paid side is every line amount,
    grouped by the agent on the line. Keys match the tie-out output: carrier, or agent_npn.
    """
    lines = world.tables["commission_lines"]
    periods: dict[str, list[str]] = {}
    for ln in lines:
        if ln["statement_period"] not in periods.setdefault(ln["carrier"], []):
            periods[ln["carrier"]].append(ln["statement_period"])
    book: dict[tuple[str, str], Decimal] = {}
    paid: dict[tuple[str, str], Decimal] = {}
    seen: set[str] = set()
    for p in world.tables["policies"]:
        first = p["policy_id"] not in seen
        seen.add(p["policy_id"])
        if not first or str(p["status"]).strip().upper() != PolicyStatus.ACTIVE:
            continue
        for period in _due_months(p, periods.get(p["carrier"], [])):
            amount = expected_amount(p["line_of_business"], p["effective_date"], period)
            for key in (("carrier", p["carrier"]), ("agent_npn", _agent(p["writing_agent_npn"]))):
                book[key] = book.get(key, Decimal("0")) + amount
    for ln in lines:
        for key in (("carrier", ln["carrier"]), ("agent_npn", _agent(ln["agent_npn"]))):
            paid[key] = paid.get(key, Decimal("0")) + ln["amount"]
    defects = []
    for field, value in sorted(book.keys() | paid.keys()):
        expected, got = book.get((field, value), ZERO), paid.get((field, value), ZERO)
        if abs(got - expected) > expected * TOTAL_TOLERANCE:
            defects.append(
                defect(
                    "statement_total_variance",
                    "commission_lines",
                    {field: value},
                    "TIE-005",
                    book_expected=expected.quantize(ZERO),
                    statement_paid=got.quantize(ZERO),
                    difference=(got - expected).quantize(ZERO),
                )
            )
    return defects
