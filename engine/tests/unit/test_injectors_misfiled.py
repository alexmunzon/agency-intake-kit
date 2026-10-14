"""misfiled_policy: an opt-in injector that files a policy under the wrong existing client."""

import copy
import random
import re
from collections import Counter
from functools import cache
from typing import Any

from synth_agency_data.injectors import INJECTORS, Defect, inject, lock_key
from synth_agency_data.injectors.base import line_key
from synth_agency_data.injectors.policies import misfiled_policy
from synth_agency_data.world import World, build_world

RATE = 0.005


@cache
def small() -> World:
    return build_world(seed=42, n_clients=200)


@cache
def injected() -> tuple[World, tuple[Defect, ...]]:
    world, defects = inject(build_world(seed=42, n_clients=2000))
    return world, tuple(defects)


def _key(client: dict[str, Any]) -> tuple[str, Any]:
    name = client["first_name"] + client["last_name"]
    return re.sub(r"[^a-z]", "", name.lower()), client["dob"]


def _line_key(line: dict[str, Any]) -> tuple[str, Any]:
    return re.sub(r"[^a-z]", "", line["member_name"].lower()), line["member_dob"]


def _check(before: World, after: World, defects: list[Defect]) -> None:
    policies = before.tables["policies"]
    assert len(defects) == max(1, round(RATE * len(policies)))
    clients = {c["client_id"]: c for c in before.tables["clients"]}
    counts = Counter(_key(c) for c in before.tables["clients"])
    old = {p["policy_id"]: p for p in policies}
    new = {p["policy_id"]: p for p in after.tables["policies"]}
    sources, targets = set(), set()
    for d in defects:
        assert d["defect_type"] == "misfiled_policy"
        assert d["source"] == "policies" and d["scored"] is True
        assert d["expected_rule_ids"] == ["REF-002"]
        assert set(d["record_key"]) == {"policy_id"}
        pid = d["record_key"]["policy_id"]
        source, target = old[pid]["client_id"], new[pid]["client_id"]
        assert d["injected_values"] == {"field": "client_id", "from": source, "to": target}
        assert target != source and target in clients  # a different, existing client
        assert counts[_key(clients[source])] == 1 and counts[_key(clients[target])] == 1
        for k in (lock_key(d["record_key"]), lock_key({"client_id": source})):
            assert k not in before.locked
        assert lock_key({"client_id": target}) not in before.locked
        assert {lock_key({"client_id": source}), lock_key({"client_id": target})} <= after.locked
        # The carrier still names the original client, by member id and policy number.
        lines = [
            ln
            for ln in after.tables["commission_lines"]
            if ln["policy_ref"] == pid and ln["carrier_member_id"] == old[pid]["carrier_member_id"]
        ]
        assert lines and all(_line_key(ln) == _key(clients[source]) for ln in lines)
        sources.add(source)
        targets.add(target)
    # No client is used twice, so each planted case stands alone.
    assert len(sources) == len(targets) == len(defects) and not sources & targets
    # Only client_id changed, and only on the picked policies.
    moved = {d["record_key"]["policy_id"] for d in defects}
    for pid, p in new.items():
        expected = old[pid] if pid not in moved else {**old[pid], "client_id": p["client_id"]}
        assert p == expected


def test_misfiled_policy_on_a_clean_world() -> None:
    world = small()
    before = copy.deepcopy(world.tables)
    out, defects = misfiled_policy(world, random.Random(1), RATE)
    assert world.tables == before  # the input is never changed
    _check(world, out, defects)


def test_misfiled_policy_is_deterministic() -> None:
    a = misfiled_policy(small(), random.Random(7), RATE)
    b = misfiled_policy(small(), random.Random(7), RATE)
    assert a[1] == b[1] and a[0].tables["policies"] == b[0].tables["policies"]


def test_misfiled_policy_respects_other_defects_after_inject() -> None:
    world, _ = injected()
    out, defects = misfiled_policy(world, random.Random(3), RATE)
    _check(world, out, defects)


def test_misfiled_policy_is_opt_in() -> None:
    assert misfiled_policy not in {fn for fn, _ in INJECTORS}


MEDICARE = {"MA", "PDP", "MEDSUPP"}


def _age(born: Any, on: Any) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def test_misfiled_policy_skips_policies_whose_lines_carry_a_defect() -> None:
    # Stacking hid planted TIE-003 cases at scale: a moved policy's lines go ambiguous, so the
    # off-schedule check never runs on them. Lines with a planted defect are locked.
    world, _ = injected()
    out, defects = misfiled_policy(world, random.Random(3), RATE)
    old = {p["policy_id"]: p for p in world.tables["policies"]}
    for d in defects:
        p = old[d["record_key"]["policy_id"]]
        for ln in world.tables["commission_lines"]:
            if ln["policy_ref"] == p["policy_id"] or (
                ln["carrier"] == p["carrier"] and ln["carrier_member_id"] == p["carrier_member_id"]
            ):
                assert lock_key(line_key(ln)) not in world.locked


def test_misfiled_policy_moves_only_onto_a_compatible_client() -> None:
    """The misfile is the only inconsistency: no MBI-002, MBI-003 or DOB-003 knock-on."""
    world, _ = injected()
    out, defects = misfiled_policy(world, random.Random(3), RATE)
    clients = {c["client_id"]: c for c in world.tables["clients"]}
    new = {p["policy_id"]: p for p in out.tables["policies"]}
    for d in defects:
        p = new[d["record_key"]["policy_id"]]
        target = clients[p["client_id"]]
        medicare = str(p["line_of_business"]) in MEDICARE
        assert bool(target["mbi"]) == medicare
        if medicare and p["eligibility_reason"] not in ("DISABILITY", "ESRD"):
            assert _age(target["dob"], p["effective_date"]) >= 65
