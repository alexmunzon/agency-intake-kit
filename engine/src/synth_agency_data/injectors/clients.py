"""Client defects: address, MBI, identity edits, and copied clients."""

import random
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from agency_schema.formats import zip3_table
from synth_agency_data.injectors.base import Defect, defect, edit, pick
from synth_agency_data.world import AS_OF, Row, World

BAD_MBI_LETTERS = "BILOSZ"  # letters the MBI format never uses
NICKNAMES = {
    "Robert": "Bob", "William": "Bill", "Richard": "Rick", "James": "Jim", "John": "Jack",
    "Michael": "Mike", "Joseph": "Joe", "Thomas": "Tom", "Charles": "Chuck", "David": "Dave",
    "Daniel": "Dan", "Christopher": "Chris", "Elizabeth": "Liz", "Jennifer": "Jen",
    "Margaret": "Peggy", "Patricia": "Pat", "Susan": "Sue", "Deborah": "Debbie",
    "Katherine": "Kate", "Kimberly": "Kim", "Anthony": "Tony", "Matthew": "Matt",
}  # fmt: skip


def zip_state_mismatch(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    def change(c: Row) -> dict[str, str]:
        other = sorted(z for z, states in zip3_table().items() if c["state"] not in states)
        return {"zip": rng.choice(other) + c["zip"][3:]}

    rows = pick(rng, world, "clients", rate, "client_id")
    return edit(world, "clients", rows, change, "zip_state_mismatch", "ADR-002", "client_id")


def invalid_mbi(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "clients", rate, "client_id", lambda c: c["mbi"] is not None)
    return edit(
        world,
        "clients",
        rows,
        lambda c: {"mbi": c["mbi"][0] + rng.choice(BAD_MBI_LETTERS) + c["mbi"][2:]},
        "invalid_mbi",
        "MBI-001",
        "client_id",
    )


def missing_mbi(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    """MBI-003 fires once per Medicare policy of the client; the key is the client."""
    rows = pick(rng, world, "clients", rate, "client_id", lambda c: c["mbi"] is not None)
    return edit(
        world, "clients", rows, lambda c: {"mbi": None}, "missing_mbi", "MBI-003", "client_id"
    )


def _typo(name: str, rng: random.Random) -> str:
    if len(name) < 4:
        return name + name[-1]
    i = rng.randrange(1, len(name) - 1)
    return name[:i] + name[i + 1 :]


def name_typo(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "clients", rate, "client_id")
    return edit(
        world,
        "clients",
        rows,
        lambda c: {"last_name": _typo(c["last_name"], rng)},
        "name_typo",
        None,
        "client_id",
    )


def nickname(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    rows = pick(rng, world, "clients", rate, "client_id", lambda c: c["first_name"] in NICKNAMES)
    return edit(
        world,
        "clients",
        rows,
        lambda c: {"first_name": NICKNAMES[c["first_name"]]},
        "nickname",
        None,
        "client_id",
    )


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _dob_edit(
    world: World, rng: random.Random, rate: float, name: str, new_dob: Callable[[date], date | None]
) -> tuple[World, list[Defect]]:
    """Change a birth date only where every age that matters (today, each policy start) holds."""
    starts: dict[str, list[date]] = {}
    for p in world.tables["policies"]:
        starts.setdefault(p["client_id"], []).append(p["effective_date"])

    def safe(c: Row) -> bool:
        new = new_dob(c["dob"])
        dates = [AS_OF, *starts.get(c["client_id"], [])]
        return new is not None and all(_age(new, d) == _age(c["dob"], d) for d in dates)

    rows = pick(rng, world, "clients", rate, "client_id", safe)
    return edit(
        world, "clients", rows, lambda c: {"dob": new_dob(c["dob"])}, name, None, "client_id"
    )


def _swap_day_digits(dob: date) -> date | None:
    try:
        new = dob.replace(day=int(f"{dob.day:02d}"[::-1]))
    except ValueError:
        return None
    return new if new != dob else None


def _swap_month_day(dob: date) -> date | None:
    return (
        dob.replace(month=dob.day, day=dob.month)
        if dob.day <= 12 and dob.day != dob.month
        else None
    )


def dob_transposition(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    return _dob_edit(world, rng, rate, "dob_transposition", _swap_day_digits)


def dob_month_day_swap(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    return _dob_edit(world, rng, rate, "dob_month_day_swap", _swap_month_day)


def _copies(
    world: World, rng: random.Random, rate: float, name: str, rule_id: str | None
) -> tuple[World, list[Defect]]:
    """Add a second client record for an existing person (a re-keyed CRM entry, no policies)."""
    clients = list(world.tables["clients"])
    defects = []
    for i in pick(rng, world, "clients", rate, "client_id"):
        src = clients[i]
        new_id = f"C-{len(clients) + 1:05d}"
        last = src["last_name"] if rule_id else _typo(src["last_name"], rng)
        clients.append(
            {**src, "client_id": new_id, "last_name": last, "household_id": None, "email": None}
        )
        if rule_id:
            # DUP-002 flags every client in the group, so the original is a scored defect too
            # (same group, the copy's id). Otherwise its CRM rows would count as false positives.
            defects.append(
                defect(name, "clients", {"client_id": src["client_id"]}, rule_id, copied_to=new_id)
            )
        defects.append(
            defect(
                name,
                "clients",
                {"client_id": new_id},
                rule_id,
                copy_of=src["client_id"],
                last_name=last,
            )
        )
    return replace(world, tables={**world.tables, "clients": clients}), defects


def name_dob_collision(world: World, rng: random.Random, rate: float) -> tuple[World, list[Defect]]:
    return _copies(world, rng, rate, "name_dob_collision", "DUP-002")


def near_duplicate_client(
    world: World, rng: random.Random, rate: float
) -> tuple[World, list[Defect]]:
    return _copies(world, rng, rate, "near_duplicate_client", None)
