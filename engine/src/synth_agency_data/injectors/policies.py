"""Policy defects: agent ids, plan ids, dates, statuses, duplicates, and broken references."""

import random
import re
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from agency_schema.enums import EligibilityReason, PolicyStatus
from agency_schema.enums import LineOfBusiness as Lob
from synth_agency_data.injectors.base import Defect, defect, edit, line_key, lock_key, pick
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


def _name_key(name: str) -> str:
    """Lowercase letters only, the same key intake uses to match a person by name."""
    return re.sub(r"[^a-z]", "", name.lower())


_NOT_AGE_REASONS = {EligibilityReason.DISABILITY, EligibilityReason.ESRD}


def misfiled_policy(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """File a policy under a different, existing client (REF-002).

    Opt in only: it is not in the default INJECTORS list, because adding it there would change
    the random sequence and the committed demo fixture. Tests and scale-test scripts call it
    after inject().

    Commission lines are built with the world and copy the member name and DOB from the client
    the policy belonged to then; no writer rebuilds them. So after the move, the carrier lines
    (same member id and policy number) still name the original client. Only policies whose lines
    name exactly their current client are picked, and both the original and the new client must
    have a (name key, DOB) that no other client shares, so the rule has one clear answer. Both
    clients are locked and each is used once, so no other defect lands on them.

    The misfile must be the only new problem. A policy whose commission lines already carry a
    planted defect is skipped (its lines would go ambiguous and hide that defect, as seen for
    TIE-003 at scale). The new client must fit the policy: an MBI exactly when the policy is
    Medicare (else MBI-002 or MBI-003), and age 65 or over at the effective date for a
    Medicare policy not held for disability or ESRD (else DOB-003).
    """
    policies = world.tables["policies"]
    clients = world.tables["clients"]
    by_id = {c["client_id"]: c for c in clients}

    def person(c: Row) -> tuple[str, object]:
        return _name_key(c["first_name"] + c["last_name"]), c["dob"]

    counts = Counter(person(c) for c in clients)

    def free(client_id: str) -> bool:
        c = by_id.get(client_id)
        return (
            c is not None
            and counts[person(c)] == 1
            and lock_key({"client_id": client_id}) not in world.locked
        )

    def fits(p: Row, client_id: str) -> bool:
        c = by_id[client_id]
        medicare = p["line_of_business"] != Lob.ACA
        if bool(c["mbi"]) != medicare:
            return False
        if not medicare or p["eligibility_reason"] in _NOT_AGE_REASONS:
            return True
        born, on = c["dob"], p["effective_date"]
        age: int = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
        return age >= 65

    stacked: set[tuple[str, str]] = set()  # (carrier, policy id or member id) with a locked line
    named: dict[tuple[str, str], set[tuple[str, object]]] = {}
    for ln in world.tables["commission_lines"]:
        if lock_key(line_key(ln)) in world.locked:
            stacked |= {(ln["carrier"], ln["policy_ref"]), (ln["carrier"], ln["carrier_member_id"])}
        who = (_name_key(ln["member_name"] or ""), ln["member_dob"])
        named.setdefault((ln["policy_ref"], ln["carrier_member_id"]), set()).add(who)
    policy_ids = Counter(p["policy_id"] for p in policies)

    def eligible(p: Row) -> bool:
        return (
            policy_ids[p["policy_id"]] == 1
            and (p["carrier"], p["policy_id"]) not in stacked
            and (p["carrier"], p["carrier_member_id"]) not in stacked
            and lock_key({"policy_id": p["policy_id"]}) not in world.locked
            and free(p["client_id"])
            and named.get((p["policy_id"], p["carrier_member_id"]))
            == {person(by_id[p["client_id"]])}
        )

    candidates = [i for i, p in enumerate(policies) if eligible(p)]
    rng.shuffle(candidates)
    targets = sorted(c["client_id"] for c in clients if free(c["client_id"]))
    want = min(max(1, round(rate * len(policies))), len(candidates))
    used: set[str] = set()
    moves: dict[int, str] = {}
    to: dict[str, str] = {}  # policy id -> new client id (policy ids are unique here)
    for i in candidates:
        if len(moves) == want:
            break
        source = policies[i]["client_id"]
        options = [t for t in targets if t != source and t not in used and fits(policies[i], t)]
        if source in used or not options:
            continue
        target = rng.choice(options)
        moves[i] = target
        to[policies[i]["policy_id"]] = target
        used |= {source, target}
    out, defects = edit(
        world,
        "policies",
        sorted(moves),
        lambda p: {"client_id": to[p["policy_id"]]},
        "misfiled_policy",
        "REF-002",
        "policy_id",
    )
    locks = {lock_key({"client_id": c}) for c in used}
    locks |= {lock_key(d["record_key"]) for d in defects}
    return replace(out, locked=out.locked | locks), defects


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
