# Rule catalog

Generated from the rule registry by `uv run intake rules --md > ../docs/rules.md`. Do not edit
by hand. Rules appear here as their PRs land; the full planned list is BUILD-GUIDE section 6.

Severity decides what happens to a row: a blocker stops the run, an error keeps the row out of
the load file, a warning passes with a flag, and info is only logged.

| Rule | Severity | Family | Blocks the run | What it checks |
|---|---|---|---|---|
| ADR-001 | Error | ADR | no | ZIP not 5 or 9 digits |
| ADR-002 | Error | ADR | no | ZIP prefix inconsistent with state |
| ADR-003 | Error | ADR | no | State code invalid |
| CON-001 | Warning | CON | no | Email syntax invalid |
| CON-002 | Warning | CON | no | Phone cannot be normalized to 10 digits |
| DAT-001 | Error | DAT | no | Effective (or termination) date unparseable |
| DAT-002 | Error | DAT | no | Termination before effective |
| DAT-003 | Error | DAT | no | Status ACTIVE but termination date in past |
| DAT-004 | Info | DAT | no | MA or PDP effective date not the first of a month |
| DOB-001 | Error | DOB | no | DOB unparseable |
| DOB-002 | Error | DOB | no | Age outside 0 to 115 (a future DOB counts) |
| DOB-003 | Warning | DOB | no | Medicare policy, age under 65 at effective date, eligibility_reason not DISABILITY or ESRD |
| MBI-001 | Error | MBI | no | MBI format invalid |
| MBI-002 | Warning | MBI | no | MBI present on a non-Medicare policy |
| MBI-003 | Warning | MBI | no | Medicare policy missing MBI |
| NPN-001 | Error | NPN | no | NPN not 1 to 10 digits |
| NPN-002 | Error | NPN | no | Writing agent not in roster |
| PLN-001 | Error | PLN | no | Medicare plan ID malformed (MA and PDP only) |
| PLN-002 | Error | PLN | no | HIOS plan ID malformed (ACA only) |
| PLN-003 | Error | PLN | no | Plan ID prefix disagrees with line of business (MA and PDP only) |
| PLN-004 | Error | PLN | no | Medigap plan letter invalid (MEDSUPP only) |
| STA-001 | Warning | STA | no | Status value not recognized |
