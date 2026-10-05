# Canonical schema

The shape every source file is mapped into. Code: `engine/src/agency_schema/`. Synthetic data only.
`agency_schema.json_schema()` returns the JSON Schema for all of it (PR 1b wraps it in `intake schema`).

## Ground rules

- **No defaults.** A field that may be blank is "may be empty" below, but the producer must still pass it (as `None`). A forgotten column fails loudly instead of becoming a silent blank.
- **Blank means empty, once.** "May be empty" means `None`. An empty string is refused, so there is only one kind of missing.
- **No silent conversions.** Whole numbers and yes/no fields refuse text such as "2026" or "yes". Turning messy words into values is the mapping step's job, done openly. List fields are fixed tuples, so a row cannot change after it is checked.
- **No extra fields.** A model refuses any field it does not know, so a stray column (an SSN, say) cannot ride along.
- **Lineage on every row** of every table.
- **Money is exact.** `monthly_premium` and `amount` are decimals to the cent, never floats, so tie-out tolerances do not drift. Later PRs must use a matching decimal type in polars and DuckDB.
- **Models check types, rules check formats.** A malformed MBI or ZIP is still a string here. Rules decide validity and report it as an `ExceptionRecord`.

## Lineage

| Field | Type | Notes |
|---|---|---|
| source_file | text | |
| sheet | text, may be empty | empty for CSV files |
| row_number | whole number, 1 or more | row in the source file |
| raw_hash | sha256, 64 hex characters | hash of the raw row |
| run_id | text | |
| mapping_version | text | |

## Tables

Every table also has `lineage` (required).

**clients** (key: client_id): client_id, first_name, last_name, dob (date), phone (may be empty), email (may be empty), address_line1, city, state, zip, mbi (may be empty), household_id (may be empty), notes (may be empty; free text that must pass the PII gate before any log or model call).

**households** (key: household_id): household_id, primary_client_id, members (list of client_ids, at least one).

**agents** (key: npn): npn, first_name, last_name, email (may be empty), license_states (list), upline_npn (may be empty), status (AgentStatus).

**rts** (key: npn, carrier, state, plan_year, line_of_business): npn, carrier, state, plan_year (whole number), line_of_business, appointed (yes/no), certified (yes/no), effective_date, end_date (may be empty).

**policies** (key: policy_id): policy_id, client_id, carrier, plan_id (Medicare contract-plan ID, Medigap letter, or HIOS ID depending on line of business), line_of_business, state (may be empty; falls back to the client's address state), eligibility_reason (may be empty; empty for ACA), effective_date, termination_date (may be empty), status (PolicyStatus), writing_agent_npn, monthly_premium (money, may be empty), carrier_member_id (may be empty).

**commission_lines** (key: carrier, statement_period, line_no): carrier, statement_period (YYYY-MM), line_no (1 or more), carrier_member_id, member_name, member_dob, policy_ref, agent_npn (each may be empty), amount (money; negative for chargebacks), commission_type, paid_date (may be empty).

## Closed lists (enums)

| Enum | Values |
|---|---|
| LineOfBusiness | MA, PDP, MEDSUPP, ACA |
| PolicyStatus | ACTIVE, PENDING, TERMINATED, CANCELLED, UNKNOWN |
| AgentStatus | ACTIVE, INACTIVE, UNKNOWN |
| CommissionType | NEW, RENEWAL, OVERRIDE, CHARGEBACK |
| EligibilityReason | AGE, DISABILITY, ESRD |
| Severity | BLOCKER, ERROR, WARNING, INFO |
| Family | ING, MAP, SSN, CMP, DOB, MBI, NPN, PLN, ADR, CON, DAT, STA, DUP, REF, RTS, LIC, TIE, PII |
| Lane | SUGGESTED_FIX, REVIEW, BUSINESS_EVENT, UNREVIEWED |

Carrier is not an enum. It is open text, normalized by dictionary and then Jev.

## ExceptionRecord

Every stage reports problems in this one shape. All fields are required; "may be empty" means pass `None`.

| Field | Notes |
|---|---|
| id | unique per run |
| rule_id | like DOB-001; the first three letters must equal `family` |
| severity, family | from the closed lists above |
| source | which source in the drop, for example `crm` |
| row_number, raw_hash, field | may be empty for file-level problems such as CMP-001 |
| value_minimized | may be empty; must come from `minimize_value()` |
| message, suggested_fix | plain language; suggested_fix may be empty |
| blocks_load | true exactly when severity is BLOCKER |
| lane | UNREVIEWED until triage (PR 11) sets it |
| lineage | the full source row (file, sheet, row, hash, run, mapping version); must match row_number and raw_hash; empty for file-level problems |
| jev | may be empty; otherwise entry_error_probability (0 to 1), impact_score, pii_probability (0 to 1), each may be empty |

The record refuses to exist when:
- severity is BLOCKER for anything other than MAP-003, CMP-001, or SSN-001 (or one of those three is not a BLOCKER),
- `blocks_load` disagrees with severity,
- `value_minimized` does not have the shape `minimize_value()` produces (more readable characters than the masking rule keeps, or longer than 32 characters plus `...`), which means a raw value slipped through,
- a row-level problem has no lineage, or lineage that disagrees with row_number or raw_hash (or a file-level problem carries lineage),
- `message` or `suggested_fix` contains a dashed or spaced SSN (`123-45-6789`, `123 45 6789`). Bare 9-digit numbers are allowed, because NPNs can be 9 digits. Messages must never embed a raw value; rules put the masked value in `value_minimized`.

**Masking.** `minimize_value()` keeps up to two leading characters (never more than a third of the value) and all punctuation, turns every other letter or digit into `*`, and cuts anything longer than 32 characters with `...`. So `1958-03-12` becomes `19**-**-**` and `HL-998213` becomes `HL-******`, `TX` becomes `**`, and an empty value becomes `None`.

## Rule registry

`agency_schema.registry` holds the `@rule(rule_id, severity, family, description, blocks=...)` decorator, `catalog()`, and `run_rules(frame, family=None)`. Registering applies the same identity checks as ExceptionRecord, refuses duplicate ids, and `run_rules` refuses a rule that emits a record under another rule's id or severity. Rules arrive from PR 4 onward.

## Format rules

Pure functions in `agency_schema.formats`. Each takes a raw string and never raises. Models never call them; the row rules (PR 8) do, and report failures as `ExceptionRecord`s.

| Function | Accepts | Notes |
|---|---|---|
| `is_valid_mbi` | 11 characters: C A AN N A AN N A A N N | C is 1 to 9, N a digit, A a letter except S L O I B Z, AN either. Dashes, outer spaces, and lowercase are allowed. |
| `is_valid_npn` | 1 to 10 digits, no leading zero | |
| `parse_medicare_plan_id` | `H1234-005`, `H1234-005-002` | Returns prefix, contract (`H1234`), plan, and segment, or None. H and R are MA, S is PDP (`.line_of_business`). |
| `is_valid_medigap_letter` | A B C D F G K L M N | Optionally "Plan G" or "F High Deductible", any case. |
| `is_valid_hios_plan_id` | `12345TX1234567`, optional `-01` | Letters must be capitals. |
| `zip3_matches_state` | `90012` or `90012-1234` plus a state code | True when the ZIP's first three digits belong to that state in `data/zip3_state.csv`. |
| `normalize_phone` | any punctuation | Ten digits, a leading 1 and any extension dropped, or None. |
| `normalize_email` | | Trimmed and lowercased, or None if it is not name@domain.tld. |
| `normalize_name` | | For matching only: `O'Brien, Jr.` becomes `obrien` and `DE LA CRUZ` becomes `de la cruz`. Drops Jr, Sr, II, III. |
| `parse_date_loose` | see below | Returns a date or None. |

**Dates.** `parse_date_loose` reads `2025-09-01` (a time after it is ignored), `09/01/2025` or `9/1/2025` (month first), `01-Sep-25`, compact `20260501` (exactly eight digits read as year, month, day, with a year from 1900 to 2099), and Excel serial numbers from 20000 to 60000 (`45901` is 2025-09-01). Eight digits are never read as a serial, and serials have five digits, so the two shapes cannot be confused; an eight-digit value that is not a real yyyymmdd date (`20261301`, `01052026`, `00045901`) gives None. Impossible dates such as 02/30/2025 give None, and so do day-first dates such as 13/01/2025.

**Two-digit years use a 1930 to 2029 pivot.** `30` to `99` mean 1930 to 1999, and `00` to `29` mean 2000 to 2029. So `05/01/29` becomes 1 May 2029, a future date. A two-digit birth year can never mean the 1920s, so PR 8's date rules must flag a future date of birth rather than trust it.

### ZIP prefix table

`engine/src/agency_schema/data/zip3_state.csv` has one row per prefix and state (`zip3,state`): 939 rows and 933 prefixes. It covers all 50 states, DC, PR, VI, GU, AS, MP, FM, MH, PW, and the military codes AA, AE, AP. A prefix used by several places has one row each: 967 is HI and AS, and 969 is GU, MP, PW, FM, and MH.

Source: USPS Labeling List L002, 3-Digit ZIP Code Prefix Matrix, January 2011 edition (https://pe.usps.com/Archive/HTML/DMMArchive20110102/L002.htm, read 2026-10-04). The current L002 page no longer loads, so this is the newest copy we could read.

Limits, stated plainly:

- **No second source.** The plan was to cross-check against a second public list. Wikipedia's list no longer loads, and other sites could only be read through a summarizing tool that returned wrong states, so the cross-check was dropped (Alex's decision, 2026-10-04).
- **Facility versus state.** L002 names the mail sorting facility, which is sometimes in a neighboring state. These prefixes were corrected by hand to the state the addresses are in: NH 035 to 037, ME 039, VA 201, WV 267, SC 297 to 299, KY 410 to 412 and 424, IN 470 and 471, IA 515 and 516, WI 540, MN 567, IL 620, 622, 623, MO 634 and 635, AR 723, OK 739, ID 838, AZ 865, CA 961, OR 979, WA 994, and VI 008. Prefix 569 (DC) is not in L002 but was added.
- **2011 data.** A prefix put into use after 2011 is missing and will fail the check for every address under it. If ZIP rules flag a cluster of valid addresses, check this table first.
- Fishers Island, NY uses prefix 063, which the table keeps as CT only.
