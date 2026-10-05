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
# Encodings tried in order, strictly; the last never fails. A UTF-8 marker is not trusted.
READER_ENCODINGS: Final[tuple[str, ...]] = ("utf-8", "latin-1")
DEFAULT_ENCODING: Final[str] = "utf-8"  # anything else is noted as ING-001
READER_DELIMITERS: Final[str] = ",;\t|"  # candidates, the first is the fallback
SNIFF_SAMPLE_LINES: Final[int] = 50  # lines used to guess the delimiter
HEADER_SCAN_ROWS: Final[int] = 20  # how far down to look for the header row
HEADER_MIN_TEXT_SHARE: Final[float] = 0.6  # share of cells that must be words in a header
TOTAL_ROW_WORDS: Final[frozenset[str]] = frozenset(
    {"total", "subtotal", "sub total", "grand total"}
)
RAW_MAPPING_VERSION: Final[str] = "unmapped"  # lineage mapping_version before PR 5 maps headers
SSN_HEADER_WORDS: Final[frozenset[str]] = frozenset({"ssn", "ssns", "social", "tin", "taxpayer"})
SSN_HEADER_PHRASES: Final[tuple[str, ...]] = ("tax id", "soc sec", "s s n")  # header text, spaced
SSN_VALUE_PATTERN: Final[str] = r"^\d{9}$"  # a bare nine-digit cell (weak evidence)
SSN_MIN_SHARE: Final[float] = 0.9  # share of bare 9-digit cells that makes a column weak evidence
SSN_SHAPED_MIN_SHARE: Final[float] = 0.01  # share of cells holding dashed or spaced SSN text
# Canonical id fields. A header the PR 5 synonym table maps to one of these is never SSN-001
# on its values alone, even when they are nine digits.
SSN_ID_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "client_id",
        "household_id",
        "phone",
        "zip",
        "mbi",
        "policy_id",
        "plan_id",
        "npn",
        "writing_agent_npn",
        "agent_npn",
        "upline_npn",
        "carrier_member_id",
        "policy_ref",
        "line_no",
    }
)
SSN_HEADER_MASK_DIGITS: Final[int] = 9  # a header with this many digits is masked in messages
# Header words of known id fields (NPN, MBI, policy, member, phone, ZIP, plan ids), for
# headers the synonym table does not know. Same effect as SSN_ID_FIELDS.
SSN_ID_HEADER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "npn",
        "mbi",
        "medicare",
        "policy",
        "member",
        "mbr",
        "subscriber",
        "insured",
        "phone",
        "tel",
        "mobile",
        "cell",
        "fax",
        "zip",
        "postal",
        "plan",
        "contract",
        "hios",
        "line",
        "seq",
        "ref",
        "client",
        "household",
        "agent",
        "producer",
        "upline",
        "license",
    }
)

# PR 5: synonym mapping (required canonical fields per table, MAP-003)
# A required field must come from some mapped column, or MAP-003 blocks the run. These are
# the fields docs/schema.md says may not be empty, minus the ones no column supplies:
# lineage (added by readers), households (built from clients), and commission_lines.carrier
# (taken from the statement's file name).
REQUIRED_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "clients": (
        "client_id",
        "first_name",
        "last_name",
        "dob",
        "address_line1",
        "city",
        "state",
        "zip",
    ),
    "policies": (
        "policy_id",
        "client_id",
        "carrier",
        "plan_id",
        "line_of_business",
        "effective_date",
        "status",
        "writing_agent_npn",
    ),
    "agents": ("npn", "first_name", "last_name", "license_states", "status"),
    "rts": (
        "npn",
        "carrier",
        "state",
        "plan_year",
        "line_of_business",
        "appointed",
        "certified",
        "effective_date",
    ),
    "commission_lines": ("statement_period", "line_no", "amount", "commission_type"),
}
# The CRM has one row per policy, so its client id column fills policies.client_id too.
CARRIED_FIELDS: Final[dict[str, str]] = {"policies.client_id": "clients.client_id"}
MAP_CANDIDATE_MIN_SCORE: Final[float] = 0.5  # how close a header must be to be offered
MAP_CANDIDATE_LIMIT: Final[int] = 3  # candidates listed in a MAP-001 suggested fix

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
# Plan year is the policy's effective year. When True, a December effective date counts toward
# the next plan year (an AEP sale keyed early). The synthetic world keys plan year to the
# effective year, so this stays False.
PLAN_YEAR_DECEMBER_ROLLS_FORWARD: Final[bool] = False
LIST_SEPARATOR: Final[str] = "|"  # how canonical CSVs join list fields such as license_states
RTS_TRUE_VALUES: Final[frozenset[str]] = frozenset(
    {"true", "yes", "y", "1"}
)  # appointed, certified

# PR 10: three-way tie-out (tolerances: $1 or 1 percent per line, 0.5 percent on totals)
TIE_LINE_TOLERANCE_USD: Final[Decimal] = Decimal("1.00")  # a line passes within $1 ...
TIE_LINE_TOLERANCE_PCT: Final[Decimal] = Decimal("0.01")  # ... or 1 percent, whichever is larger
TIE_TOTAL_TOLERANCE_PCT: Final[Decimal] = Decimal("0.005")  # carrier and agent totals: 0.5 percent

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
# PII gate fix (#55): a relationship word followed by a capitalized name redacts the name
PII_RELATION_WORDS: Final[frozenset[str]] = frozenset(
    {"daughter", "son", "spouse", "wife", "husband", "mother", "father", "brother", "sister"}
    | {"caregiver", "grandson", "granddaughter", "niece", "nephew", "partner"}
)

# PR 12: run orchestration

# PR 17: header mapping benchmark
# The benchmark mirrors SPEC's mapping cutoff: a Jev answer under 0.60 leaves the header
# unmapped. PR 7 owns the pipeline's own cutoffs; this one only scores the benchmark.
BENCH_JEV_MIN_CONFIDENCE: Final[float] = 0.60
BENCH_SONNET_MODEL: Final[str] = "claude-sonnet-5-5"
BENCH_SONNET_MAX_TOKENS: Final[int] = 2000  # room for brief thinking before a one-word answer
# Anthropic's published Sonnet price, checked 2026-10-04. An assumption for cost estimates.
SONNET_USD_PER_MTOK_IN: Final[Decimal] = Decimal("2.00")
SONNET_USD_PER_MTOK_OUT: Final[Decimal] = Decimal("10.00")
