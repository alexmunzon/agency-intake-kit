"""CRM export (AgencyBloc style): one row per policy row, client fields repeated.

Quirks: latin-1 text that starts with a UTF-8 byte order mark, Excel serial dates as text in
"Mbr DOB" (serials outside 20000 to 60000 fall back to 01/31/1950 style), three date styles
rotating by row in "Eff Date" and "Term Date", and status words in mixed case. Clients with
no policy row (re-keyed copies, or a client whose only policy was orphaned) get one row each
at the end with the policy columns blank, so every client defect has a row.
"""

import csv
import io
from pathlib import Path
from typing import Any

from synth_agency_data.world import Row, World
from synth_agency_data.writers.common import SERIAL_RANGE, excel_serial, fmt_date, text

FILE = "crm_export.csv"
BOM = b"\xef\xbb\xbf"
ENCODING = "latin-1"
HEADERS = (
    "Client ID", "Client Name", "Mbr DOB", "Primary Phone", "Email", "Address", "City",
    "State", "Zip", "Medicare ID", "Household", "Policy #", "Carrier Name", "Plan", "Product",
    "Policy State", "Eligibility", "Member ID", "Eff Date", "Term Date", "Status",
    "Writing Agent NPN", "Premium", "Notes",
)  # fmt: skip
DATE_STYLES = ("mdy", "iso", "mdy2")
CANONICAL_STATUSES = {"ACTIVE", "PENDING", "TERMINATED", "CANCELLED", "UNKNOWN"}


def _dob(c: Row | None) -> str:
    if c is None:
        return ""
    lo, hi = SERIAL_RANGE
    return fmt_date(c["dob"], "serial" if lo <= excel_serial(c["dob"]) <= hi else "mdy")


def _status(value: Any, n: int) -> str:
    word = text(value)
    if word not in CANONICAL_STATUSES:
        return word  # a planted messy status stays exactly as injected
    return (word.title(), word, word.lower())[n % 3]


def _client_cells(c: Row | None) -> list[str]:
    if c is None:
        return [""] * 10
    return [
        f"{c['last_name']}, {c['first_name']}",
        _dob(c),
        *(text(c[k]) for k in ("phone", "email", "address_line1", "city", "state", "zip")),
        text(c["mbi"]),
        text(c["household_id"]),
    ]


def write_crm(
    world: World, notes: dict[str, str], out: Path, truncate: int | None
) -> dict[str, Any]:
    """Write the file. Returns its row count and where each policy and client landed."""
    clients = {c["client_id"]: c for c in world.tables["clients"]}
    rows: list[list[str]] = []
    policy_rows: dict[str, int] = {}
    client_rows: dict[str, int] = {}
    for n, p in enumerate(world.tables["policies"]):
        style = DATE_STYLES[n % 3]
        rows.append(
            [text(p["client_id"]), *_client_cells(clients.get(p["client_id"]))]
            + [text(p[k]) for k in ("policy_id", "carrier", "plan_id", "line_of_business")]
            + [text(p[k]) for k in ("state", "eligibility_reason", "carrier_member_id")]
            + [fmt_date(p["effective_date"], style), fmt_date(p["termination_date"], style)]
            + [_status(p["status"], n), text(p["writing_agent_npn"]), text(p["monthly_premium"])]
            + [notes.get(p["policy_id"], "")]
        )
        policy_rows[p["policy_id"]] = len(rows) + 1  # a duplicated id points at the later copy
        client_rows.setdefault(p["client_id"], len(rows) + 1)
    for c in world.tables["clients"]:
        if c["client_id"] not in client_rows:
            rows.append([c["client_id"], *_client_cells(c)] + [""] * 13)
            client_rows[c["client_id"]] = len(rows) + 1
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADERS)
    writer.writerows(rows[:truncate] if truncate is not None else rows)
    (out / FILE).write_bytes(BOM + buffer.getvalue().encode(ENCODING))
    return {"rows": len(rows), "policies": policy_rows, "clients": client_rows}
