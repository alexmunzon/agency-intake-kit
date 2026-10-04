"""The clean synthetic world: canonical tables in memory, with zero defects.

Rows are plain dicts keyed by canonical field name. They carry no lineage: per SPEC, lineage
is added when a file is read. PR 3a injects defects into a copy of this world.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

from agency_schema.enums import AgentStatus, EligibilityReason, PolicyStatus
from agency_schema.enums import LineOfBusiness as Lob
from agency_schema.formats import normalize_name, zip3_table
from synth_agency_data.rates import commission_type, expected_amount

Row = dict[str, Any]

AS_OF = date(2026, 10, 1)  # the world's "today", the same as the demo's frozen clock
STATEMENT_PERIODS = ("2026-06", "2026-07", "2026-08")
FIRST_START = date(2022, 1, 1)  # earliest policy start, which keeps the RTS table small
LAST_START = date(2026, 5, 1)  # latest start that is in force for every statement period
PENDING_START = {"medicare": date(2026, 11, 1), "aca": date(2027, 1, 1)}
PENDING_SHARE = 0.03  # of single-policy clients
DISABLED_SHARE = 0.04  # of Medicare clients: under 65 with DISABILITY or ESRD
HOUSEHOLD_RATIO = 0.7  # households per client
TRIO_SHARE = 0.03  # households with an adult child
SHARED_PHONE_SHARE = 0.6
EMAIL_SHARE = 0.8
N_AGENTS = 25  # one top, four managers, twenty producers

CARRIERS = {  # name: (dictionary alias, member id prefix). All fictional.
    "Northwind Health": ("NWH", "NW"),
    "Bluepeak": ("BPK", "BP"),
    "Harborline": ("HBL", "HL"),
    "Cardinal Mutual": ("CMU", "CM"),
    "Summit Health Plans": ("SHP", "SH"),
    "Meridian Care": ("MER", "MC"),
}
# Client profiles: share of clients, lines of business held together, switched carriers once.
# At 2,000 clients these give 2,600 policies: MA 55%, PDP 15%, MEDSUPP 10%, ACA 20%.
PROFILES: dict[str, tuple[float, tuple[Lob, ...], bool]] = {
    "ma": (0.495, (Lob.MA,), False),
    "ma_switch": (0.11, (Lob.MA,), True),
    "pdp": (0.065, (Lob.PDP,), False),
    "medsupp_pdp": (0.13, (Lob.MEDSUPP, Lob.PDP), False),
    "aca": (0.14, (Lob.ACA,), False),
    "aca_switch": (0.06, (Lob.ACA,), True),
}
NOT_STATES = {"PR", "VI", "GU", "AS", "MP", "FM", "MH", "PW", "AA", "AE", "AP"}
MBI_LETTERS = "ACDEFGHJKMNPQRTUVWXY"
MEDIGAP_LETTERS = "GGGNNFKLAB"  # G and N are the common sellers


@dataclass(frozen=True)
class World:
    seed: int
    tables: dict[str, list[Row]]


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def _month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def _random_month(rng: random.Random, lo: date, hi: date) -> date:
    return _month_start(rng.randint(_month_index(lo), _month_index(hi)))


def _dob(rng: random.Random, age: int) -> date:
    """A birth date that makes the person exactly `age` on AS_OF (AS_OF is 1 October)."""
    latest = AS_OF.replace(year=AS_OF.year - age)
    return latest - timedelta(days=rng.randrange(365))


def _first_month_at_65(dob: date) -> date:
    birthday = date(dob.year + 65, dob.month, 28) + timedelta(days=dob.day - 28)
    return birthday if birthday.day == 1 else _month_start(_month_index(birthday) + 1)


def _mbi(rng: random.Random) -> str:
    def a() -> str:
        return rng.choice(MBI_LETTERS)

    def an() -> str:
        return rng.choice(MBI_LETTERS + "0123456789")

    def n() -> str:
        return str(rng.randrange(10))

    return str(rng.randint(1, 9)) + a() + an() + n() + a() + an() + n() + a() + a() + n() + n()


def _money(rng: random.Random, lo_cents: int, hi_cents: int) -> Decimal:
    return (Decimal(rng.randint(lo_cents, hi_cents)) / 100).quantize(Decimal("0.01"))


def _unique(used: set[str], make: Any) -> str:
    while (value := make()) in used:
        pass
    used.add(value)
    return str(value)


def build_world(seed: int, n_clients: int) -> World:
    if n_clients < 1:
        raise ValueError("n_clients must be at least 1")
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    states = sorted({s for row in zip3_table().values() for s in row} - NOT_STATES)
    prefixes = {s: sorted(z for z, ss in zip3_table().items() if s in ss) for s in states}

    used_npns: set[str] = set()
    agents: list[Row] = []
    for i in range(N_AGENTS):
        upline = None if i == 0 else agents[0 if i < 5 else 1 + (i - 5) % 4]["npn"]
        agents.append(
            {
                "npn": _unique(used_npns, lambda: str(rng.randint(1_000_000, 99_999_999))),
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": f"agent{i + 1:02d}@example.com",
                "license_states": tuple(
                    sorted(rng.sample(states, 1 if i == 0 else rng.randint(2, 4)))
                ),
                "upline_npn": upline,
                "status": AgentStatus.ACTIVE,
            }
        )
    writers = agents[1:]

    plans = {
        c: {p: [f"{p}{rng.randint(1000, 9999)}" for _ in range(2)] for p in "HRS"} for c in CARRIERS
    }
    issuers = {c: f"{rng.randint(10000, 99999)}" for c in CARRIERS}

    def plan_id(carrier: str, lob: Lob, state: str) -> str:
        if lob == Lob.MEDSUPP:
            return rng.choice(MEDIGAP_LETTERS)
        if lob == Lob.ACA:
            return f"{issuers[carrier]}{state}{rng.randrange(10**7):07d}"
        prefix = "S" if lob == Lob.PDP else rng.choice("HHHHHHHHHR")
        segment = f"-{rng.randint(1, 3):03d}" if rng.random() < 0.3 else ""
        return f"{rng.choice(plans[carrier][prefix])}-{rng.randint(1, 30):03d}{segment}"

    counts = {k: round(n_clients * share) for k, (share, _, _) in PROFILES.items() if k != "ma"}
    profiles = ["ma"] * (n_clients - sum(counts.values()))
    for k, count in counts.items():
        profiles += [k] * count
    rng.shuffle(profiles)

    n_households = max(1, round(n_clients * HOUSEHOLD_RATIO))
    trios = min(round(n_households * TRIO_SHARE), (n_clients - n_households) // 2)
    pairs = n_clients - n_households - 2 * trios
    sizes = [3] * trios + [2] * pairs + [1] * (n_households - trios - pairs)
    rng.shuffle(sizes)

    clients: list[Row] = []
    households: list[Row] = []
    policies: list[Row] = []
    person_keys: set[tuple[str, date]] = set()
    member_ids: dict[str, set[str]] = {c: set() for c in CARRIERS}
    for h, size in enumerate(sizes, start=1):
        household_id, agent = f"H-{h:05d}", rng.choice(writers)
        state = rng.choice(agent["license_states"])
        zip_code = f"{rng.choice(prefixes[state])}{rng.randrange(100):02d}"
        address, city, last = fake.street_address(), fake.city(), fake.last_name()
        shared_phone = f"({rng.randint(201, 989)}) 555-01{rng.randrange(100):02d}"
        members: list[str] = []
        for _ in range(size):
            client_id = f"C-{len(clients) + 1:05d}"
            _, lobs, switched = PROFILES[profiles[len(clients)]]
            medicare = lobs[0] != Lob.ACA
            disabled = medicare and rng.random() < DISABLED_SHARE
            pending = not switched and len(lobs) == 1 and rng.random() < PENDING_SHARE
            if not medicare:
                age = rng.randint(21, 64)
            else:
                age = rng.randint(30, 63) if disabled else rng.randint(68 if switched else 66, 92)
            while True:
                first, dob = fake.first_name(), _dob(rng, age)
                key = (normalize_name(f"{first} {last}"), dob)
                if key not in person_keys:
                    person_keys.add(key)
                    break
            phone = (
                shared_phone
                if rng.random() < SHARED_PHONE_SHARE
                else (f"({rng.randint(201, 989)}) 555-01{rng.randrange(100):02d}")
            )
            slug = "".join(ch for ch in f"{first}.{last}".lower() if ch.isalnum() or ch == ".")
            clients.append(
                {
                    "client_id": client_id,
                    "first_name": first,
                    "last_name": last,
                    "dob": dob,
                    "phone": phone,
                    "email": f"{slug}{len(clients) + 1}@example.com"
                    if rng.random() < EMAIL_SHARE
                    else None,
                    "address_line1": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "mbi": _mbi(rng) if medicare else None,
                    "household_id": household_id,
                    "notes": None,
                }
            )
            members.append(client_id)

            spans: list[tuple[date, date | None]]
            if pending:
                spans = [(PENDING_START["medicare" if medicare else "aca"], None)]
            elif not medicare:
                spans = (
                    [(date(2025, 1, 1), date(2025, 12, 31)), (date(2026, 1, 1), None)]
                    if switched
                    else [(date(rng.choice((2024, 2025, 2026)), 1, 1), None)]
                )
            else:
                earliest = FIRST_START if disabled else max(FIRST_START, _first_month_at_65(dob))
                if switched:
                    old = _random_month(rng, earliest, _month_start(_month_index(LAST_START) - 12))
                    new = _random_month(rng, _month_start(_month_index(old) + 12), LAST_START)
                    spans = [(old, new - timedelta(days=1)), (new, None)]
                else:
                    spans = [(_random_month(rng, earliest, LAST_START), None)]
            reason = None
            if medicare:
                reason = (
                    rng.choice((EligibilityReason.DISABILITY,) * 4 + (EligibilityReason.ESRD,))
                    if disabled
                    else EligibilityReason.AGE
                )
            carrier = rng.choice(list(CARRIERS))
            for start, end in spans:
                for lob in lobs:
                    prefix = CARRIERS[carrier][1]
                    status = (
                        PolicyStatus.TERMINATED
                        if end
                        else PolicyStatus.PENDING
                        if start > AS_OF
                        else PolicyStatus.ACTIVE
                    )
                    policies.append(
                        {
                            "policy_id": f"P-{len(policies) + 1:05d}",
                            "client_id": client_id,
                            "carrier": carrier,
                            "plan_id": plan_id(carrier, lob, state),
                            "line_of_business": lob,
                            "state": state,
                            "eligibility_reason": reason,
                            "effective_date": start,
                            "termination_date": end,
                            "status": status,
                            "writing_agent_npn": agent["npn"],
                            "monthly_premium": _money(
                                rng,
                                *{
                                    Lob.MA: (0, 6000),
                                    Lob.PDP: (500, 9000),
                                    Lob.MEDSUPP: (9000, 32000),
                                    Lob.ACA: (15000, 90000),
                                }[lob],
                            ),
                            "carrier_member_id": _unique(
                                member_ids[carrier],
                                lambda p=prefix: f"{p}-{rng.randint(100000, 999999)}",
                            ),
                        }
                    )
                carrier = rng.choice(
                    [c for c in CARRIERS if c != carrier]
                )  # a switch changes carrier
        households.append(
            {
                "household_id": household_id,
                "primary_client_id": members[0],
                "members": tuple(members),
            }
        )

    rts_keys: set[tuple[Any, ...]] = set()
    for p in policies:
        last_day = p["termination_date"] or max(p["effective_date"], AS_OF)
        for year in range(p["effective_date"].year, last_day.year + 1):
            rts_keys.add(
                (p["writing_agent_npn"], p["carrier"], p["state"], year, p["line_of_business"])
            )
    rts = [
        {
            "npn": npn,
            "carrier": carrier,
            "state": state,
            "plan_year": year,
            "line_of_business": lob,
            "appointed": True,
            "certified": True,
            "effective_date": date(year, 1, 1),
            "end_date": None,
        }
        for npn, carrier, state, year, lob in sorted(rts_keys)
    ]

    by_id = {c["client_id"]: c for c in clients}
    lines: list[Row] = []
    for period in STATEMENT_PERIODS:
        year, month = (int(x) for x in period.split("-"))
        paid = date(year + month // 12, month % 12 + 1, 15)
        for carrier in CARRIERS:
            active = [
                p
                for p in policies
                if p["carrier"] == carrier and p["status"] == PolicyStatus.ACTIVE
            ]
            for line_no, p in enumerate(active, start=1):
                client = by_id[p["client_id"]]
                lines.append(
                    {
                        "carrier": carrier,
                        "statement_period": period,
                        "line_no": line_no,
                        "carrier_member_id": p["carrier_member_id"],
                        "member_name": f"{client['first_name']} {client['last_name']}",
                        "member_dob": client["dob"],
                        "policy_ref": p["policy_id"],
                        "agent_npn": p["writing_agent_npn"],
                        "amount": expected_amount(
                            p["line_of_business"], p["effective_date"], period
                        ),
                        "commission_type": commission_type(p["effective_date"], period),
                        "paid_date": paid,
                    }
                )

    return World(
        seed,
        {
            "clients": clients,
            "households": households,
            "agents": agents,
            "rts": rts,
            "policies": policies,
            "commission_lines": lines,
        },
    )
