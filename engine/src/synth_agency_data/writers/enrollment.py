"""Enrollment platform export (Sunfire style): one row per MA or PDP policy row.

Quirks: semicolon delimiter (UTF-8, no BOM), snake_case headers next to one header no
dictionary knows ("Birth Dt (mm/dd/yy)", SPEC example 2), two-digit birth years (every birth
year is 1930 or later, so the 1930 to 2029 pivot reads them right), compact effective dates
(20260501), and the platform's own status words.
"""

import csv
from pathlib import Path

from agency_schema.enums import LineOfBusiness as Lob
from synth_agency_data.world import World
from synth_agency_data.writers.common import fmt_date, text

FILE = "enrollment_export.csv"
DELIMITER = ";"
HEADERS = (
    "member_first", "member_last", "Birth Dt (mm/dd/yy)", "mbi", "carrier", "contract_plan",
    "effective", "agent_npn", "application_status", "policy_number",
)  # fmt: skip
APP_STATUS = {
    "ACTIVE": "Approved",
    "PENDING": "Submitted",
    "TERMINATED": "Disenrolled",
    "CANCELLED": "Withdrawn",
}


def write_enrollment(world: World, out: Path) -> int:
    clients = {c["client_id"]: c for c in world.tables["clients"]}
    rows = []
    for p in world.tables["policies"]:
        if p["line_of_business"] not in (Lob.MA, Lob.PDP):
            continue
        c = clients.get(p["client_id"], {})  # an orphan policy has no client fields
        rows.append(
            [
                text(c.get("first_name")),
                text(c.get("last_name")),
                fmt_date(c.get("dob"), "mdy2"),
                text(c.get("mbi")),
                p["carrier"],
                p["plan_id"],
                fmt_date(p["effective_date"], "compact"),
                p["writing_agent_npn"],
                APP_STATUS.get(text(p["status"]), "Unknown"),
                p["policy_id"],
            ]
        )
    with (out / FILE).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=DELIMITER, lineterminator="\n")
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return len(rows)
