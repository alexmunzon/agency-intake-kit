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
SSN_HEADER_WORDS: Final[frozenset[str]] = frozenset({"ssn", "social"})
SSN_VALUE_PATTERN: Final[str] = r"^\d{3}[- ]?\d{2}[- ]?\d{4}$"  # dashed, spaced, or 9 digits
SSN_MIN_SHARE: Final[float] = 0.9  # share of non-empty cells matching that makes a column SSNs

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

# PR 12: run orchestration
