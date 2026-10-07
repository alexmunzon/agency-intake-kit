# Rule catalog

Generated from the rule registry by `uv run intake rules --md > ../docs/rules.md`. Do not edit
by hand. All 48 rules; readers, gates, mapping, tie-out, and clean validation raise theirs
outside the registry.

Severity decides what happens to a row: a blocker stops the run, an error keeps the row out of
the load file, a warning passes with a flag, and info is only logged.

| Rule | Severity | Family | Blocks the run | What it checks |
|---|---|---|---|---|
| ADR-001 | Error | ADR | no | ZIP not 5 or 9 digits |
| ADR-002 | Error | ADR | no | ZIP prefix inconsistent with state |
| ADR-003 | Error | ADR | no | State code invalid |
| CMP-001 | Blocker | CMP | yes | Rows received differ from rows expected; runs on raw frames |
| CMP-002 | Warning | CMP | no | A source is missing entirely |
| CON-001 | Warning | CON | no | Email syntax invalid |
| CON-002 | Warning | CON | no | Phone cannot be normalized to 10 digits |
| DAT-001 | Error | DAT | no | Effective (or termination) date unparseable |
| DAT-002 | Error | DAT | no | Termination before effective |
| DAT-003 | Error | DAT | no | Status ACTIVE but termination date in past |
| DAT-004 | Info | DAT | no | MA or PDP effective date not the first of a month |
| DOB-001 | Error | DOB | no | DOB unparseable |
| DOB-002 | Error | DOB | no | Age outside 0 to 115 (a future DOB counts) |
| DOB-003 | Warning | DOB | no | Medicare policy, age under 65 at effective date, eligibility_reason not DISABILITY or ESRD |
| DUP-001 | Warning | DUP | no | Exact duplicate row |
| DUP-002 | Warning | DUP | no | Same normalized name and DOB on two or more clients (exact after normalization; fuzzy identity matching belongs to bob-resolve) |
| DUP-003 | Error | DUP | no | Duplicate policy ID with different content |
| ING-001 | Info | ING | no | File encoding was not UTF-8 |
| ING-002 | Info | ING | no | Header row was not the first row |
| ING-003 | Info | ING | no | Trailing total or blank rows dropped |
| ING-004 | Warning | ING | no | Delimiter guessed with low confidence |
| LIC-001 | Error | LIC | no | Agent license states do not include the policy state (client address state when the policy has none) |
| MAP-001 | Warning | MAP | no | Column could not be mapped |
| MAP-002 | Warning | MAP | no | Mapping confidence between thresholds, or Jev gave no usable answer |
| MAP-003 | Blocker | MAP | yes | Required canonical field missing (a drop with no CRM misses them all) |
| MAP-004 | Error | MAP | no | Canonical row violates its declared load-table schema or depends on an excluded parent |
| MAP-005 | Warning | MAP | no | Export format changed since mappings were saved; saved decisions not reused |
| MBI-001 | Error | MBI | no | MBI format invalid |
| MBI-002 | Warning | MBI | no | MBI present on a non-Medicare policy |
| MBI-003 | Warning | MBI | no | Medicare policy missing MBI |
| NPN-001 | Error | NPN | no | NPN not 1 to 10 digits |
| NPN-002 | Error | NPN | no | Writing agent not in roster |
| PII-001 | Warning | PII | no | Free text appears to contain personal health or identity details |
| PLN-001 | Error | PLN | no | Medicare plan ID malformed (MA and PDP only) |
| PLN-002 | Error | PLN | no | HIOS plan ID malformed (ACA only) |
| PLN-003 | Error | PLN | no | Plan ID prefix disagrees with line of business (MA and PDP only) |
| PLN-004 | Error | PLN | no | Medigap plan letter invalid (MEDSUPP only) |
| REF-001 | Error | REF | no | Policy references unknown client |
| RTS-001 | Error | RTS | no | Writing agent not RTS for carrier, policy state, plan year, line of business |
| RTS-002 | Warning | RTS | no | RTS record end_date before policy effective date |
| SSN-001 | Blocker | SSN | yes | A column looks like SSNs; runs on raw frames before any model call |
| STA-001 | Warning | STA | no | Status value not recognized |
| TIE-001 | Warning | TIE | no | Active policy with no commission line in period |
| TIE-002 | Error | TIE | no | Commission paid on a policy not in the book |
| TIE-003 | Warning | TIE | no | Commission amount off schedule beyond tolerance |
| TIE-004 | Warning | TIE | no | CRM status disagrees with carrier statement |
| TIE-005 | Error | TIE | no | Totals by carrier or agent off beyond tolerance, or a statement is missing |
| TIE-006 | Info | TIE | no | Match made on name plus DOB only (weak key) |
