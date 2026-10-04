"""Every threshold, tolerance, and required-field list for the intake pipeline.

Rules for this file:
- One section per PR, in PR order. Add constants only inside your own PR's section.
- Never reorder, rename, or delete an existing constant in another PR's section.
- Type every constant with Final, for example `DOB_MAX_AGE: Final[int] = 115`.
- Business limits live here, never inline in pipeline code.
"""

from decimal import Decimal
from typing import Final

# PR 4: readers and raw gates (sniffing, header detection, SSN-001, CMP-001, CMP-002)

# PR 5: synonym mapping (required canonical fields per table, MAP-003)

# PR 6: Jev client (retry and backoff, the $0.50 per-run budget)
# Endpoint, model, and price checked on docs.typesafe.ai on 2026-10-04 (see docs/jev.md).
JEV_API_URL: Final[str] = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL: Final[str] = "jev-latest"
JEV_USD_PER_MTOK_IN: Final[Decimal] = Decimal("0.042")  # dollars per million input tokens
JEV_BUDGET_USD: Final[Decimal] = Decimal("0.50")  # estimated spend that switches Jev off
JEV_MAX_TRIES: Final[int] = 5  # total tries on 429 and 529, the first one included
JEV_BACKOFF_BASE_S: Final[float] = 1.0  # first wait; doubles each retry, with jitter
JEV_TIMEOUT_S: Final[float] = 30.0  # seconds per HTTP request

# PR 7: Jev mapping and enum normalization (confidence cutoffs, MAP-002)

# PR 8: row validators (DOB age range, Medicare age, date rules)
DOB_MIN_AGE: Final[int] = 0  # DOB-002: younger than this means a birth date after the run date
DOB_MAX_AGE: Final[int] = 115  # DOB-002: older than this is usually a century error
MEDICARE_AGE: Final[int] = 65  # DOB-003: under this, Medicare needs DISABILITY or ESRD

# PR 9: cross-record checks (duplicates, references, RTS, licenses)

# PR 10: three-way tie-out (tolerances: $1 or 1 percent per line, 0.5 percent on totals)

# PR 11: exceptions policy and triage (PII gate cutoff)
TRIAGE_ENTRY_ERROR: Final[float] = 0.80  # at or above: a keying slip, suggested-fix lane
TRIAGE_BUSINESS_EVENT: Final[float] = 0.20  # at or below: a real event; in between: review
TRIAGE_SHAPE_MAX_CHARS: Final[int] = 32  # value shapes sent to Jev are cut to this length
# Fields sent with each triage question, by rule family. Notes are never among them.
TRIAGE_NEIGHBORS: Final[dict[str, tuple[str, ...]]] = {
    "DOB": ("line_of_business", "eligibility_reason"),
    "MBI": ("line_of_business",),
    "NPN": ("carrier", "agent_in_roster"),
    "PLN": ("line_of_business", "carrier"),
    "ADR": ("state",),
    "DAT": ("status", "line_of_business"),
    "STA": ("line_of_business",),
    "DUP": ("line_of_business",),
    "REF": ("line_of_business",),
    "RTS": ("carrier", "line_of_business"),
    "LIC": ("line_of_business",),
    "TIE": ("carrier", "commission_type"),
}
# Closed-vocabulary neighbors are sent as the value itself; every other field as a shape.
TRIAGE_KEEP_AS_IS: Final[frozenset[str]] = frozenset(
    {"line_of_business", "eligibility_reason", "status", "carrier", "commission_type"}
    | {"state", "agent_in_roster"}
)
PII_REDACT: Final[float] = 0.50  # PII gate: at or above, the text is redacted
PII_REDACTED_TEXT: Final[str] = "[redacted]"
# Word stems the PII pre-filter looks for (diagnosis, diagnosed, conditions, disability, ...)
PII_HEALTH_WORDS: Final[frozenset[str]] = frozenset(
    {"diagnos", "condition", "treatment", "prescription", "disabilit"}
)

# PR 12: run orchestration
