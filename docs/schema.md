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
| jev | may be empty; otherwise entry_error_probability (0 to 1), impact_score, pii_probability (0 to 1), each may be empty |

The record refuses to exist when:
- severity is BLOCKER for anything other than MAP-003, CMP-001, or SSN-001 (or one of those three is not a BLOCKER),
- `blocks_load` disagrees with severity,
- `value_minimized` does not have the shape `minimize_value()` produces (a letter or digit after the first two characters, or longer than 32 characters plus `...`), which means a raw value slipped through,
- `message` or `suggested_fix` contains an SSN-shaped value (`123-45-6789`). Messages must never embed a raw value; rules put the masked value in `value_minimized`.

**Masking.** `minimize_value()` keeps up to two leading characters (never more than a third of the value) and all punctuation, turns every other letter or digit into `*`, and cuts anything longer than 32 characters with `...`. So `1958-03-12` becomes `19**-**-**` and `HL-998213` becomes `HL-******`, `TX` becomes `**`, and an empty value becomes `None`.

## Rule registry

`agency_schema.registry` holds the `@rule(rule_id, severity, family, description, blocks=...)` decorator, `catalog()`, and `run_rules(frame, family=None)`. Registering applies the same identity checks as ExceptionRecord, refuses duplicate ids, and `run_rules` refuses a rule that emits a record under another rule's id or severity. Rules arrive from PR 4 onward.

## Format rules

Added in PR 1a-ii (`agency_schema.formats` and `data/zip3_state.csv`).
