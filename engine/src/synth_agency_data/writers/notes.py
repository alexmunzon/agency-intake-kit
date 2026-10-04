"""The CRM Notes column: a few harmless notes, plus 1 percent planted PII sentences (PII-001).

Every specific is fake on purpose: 555 phone numbers, example.com emails, zero-led account
numbers that are too short to look like an SSN, and made-up last names. Benign notes include
a few accented letters, so the latin-1 encoding of the CRM file actually matters.
"""

import random

from synth_agency_data.injectors.base import Defect, defect, lock_key
from synth_agency_data.world import World

PII_RATE = 0.01  # guide 7.3: PII in notes, 1 percent of CRM policy rows
BENIGN_RATE = 0.05
FAKE_FIRST = ("Jamie", "Robin", "Casey", "Morgan", "Taylor")
FAKE_LAST = ("Testperson", "Sampleton", "Placeholder", "Fakename")
PII_TEMPLATES = (
    "Daughter {first} {last} is the contact, cell (555) 555-01{nn}.",
    "Client gave bank account 000{n5} for the premium draft.",
    "Spouse wants copies sent to {first}.{last}@example.com.",
    "Client read out driver license TEST{n5} on the call.",
    "Card on file ends in 00{nn}, client read the full number aloud.",
)
BENIGN = (
    "Prefers mail over phone.",
    "Asked about dental add-ons at renewal.",
    "Client prefers materials en español.",
    "Met at the café seminar in the spring.",
    "Call after 2pm.",
)


def plant_notes(world: World, plant_pii: bool = True) -> tuple[dict[str, str], list[Defect]]:
    """Notes by policy_id. PII goes only on unique, undefected policies (one defect per key)."""
    rng = random.Random(f"notes-{world.seed}")
    policies = world.tables["policies"]
    seen: dict[str, int] = {}
    for p in policies:
        seen[p["policy_id"]] = seen.get(p["policy_id"], 0) + 1
    ids = [pid for pid, n in seen.items() if n == 1]
    free = [pid for pid in ids if lock_key({"policy_id": pid}) not in world.locked]
    pii = sorted(rng.sample(free, round(PII_RATE * len(policies)))) if plant_pii else []
    notes: dict[str, str] = {}
    defects = []
    for pid in pii:
        sentence = rng.choice(PII_TEMPLATES).format(
            first=rng.choice(FAKE_FIRST),
            last=rng.choice(FAKE_LAST),
            nn=f"{rng.randrange(100):02d}",
            n5=f"{rng.randrange(100000):05d}",
        )
        notes[pid] = sentence
        defects.append(
            defect(
                "pii_in_notes",
                "policies",
                {"policy_id": pid},
                "PII-001",
                field="notes",
                to=sentence,
            )
        )
    rest = [pid for pid in ids if pid not in notes]
    for pid in sorted(rng.sample(rest, round(BENIGN_RATE * len(policies)))):
        notes[pid] = rng.choice(BENIGN)
    return notes, defects
