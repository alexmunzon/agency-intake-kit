# SPEC: agency-intake-kit

The contract for every PR. Written 2026-10-04 in the SPEC session, after PR 0 (`bb0c975`).
From here on, this file overrides BUILD-GUIDE-agency-intake-kit.md wherever they disagree.
ROADMAP.md section 5 explains why the project exists. This file says what it must do.

Decisions made in the SPEC interview (2026-10-04), each reflected in the sections below:
- Alex's prepared answers in BUILD-GUIDE section 3.2 are accepted as written.
- PR 1 splits into 1a (models) and 1b (sample run, the engine-to-dashboard contract).
- PR 3 splits into 3a (defects, planted cases, a canonical-shape copy, ground truth) and 3b (the four messy source files). Rule PRs test against the 3a copy, so they do not wait for readers and mapping.
- The named records in examples 3 and 4 are planted on purpose, not hoped for, and so are the exact truncation point (example 5) and the SSN values (example 6).
- Alex has a TypeSafe key. Jev spend is capped at $0.50 per run. Missing an accuracy target fails the end-to-end test.
- The calendar holds, with two lanes running at once.
- Second review (2026-10-04): triage and PII cassettes are recorded in PR 12 against the real pipeline's requests, PR 11 deduplicates triage calls, ground truth uses stable record keys, and PR 13 copies the sample run into the dashboard.

Changes from the build guide made in PR 0: Node 24 instead of Node 20 (Node 20 reached end of life on 2026-04-30), and Next.js 16, whose `typecheck` script runs `next typegen` first.

## Business outcome

When an agency is acquired, its records arrive as a pile of mismatched files. Today someone checks them by hand for weeks. This kit takes that pile and, in one command, answers three questions an acquirer must answer within 30 days of close:

1. **Can this agency's book go live in our systems?** Every row is mapped to one standard format and checked against 46 written rules. Anything that would corrupt the load blocks it, with a plain-language reason and a suggested fix.
2. **Does the money agree?** The book of business, the carrier commission statements, and the CRM are reconciled three ways, with every dollar variance explained.
3. **Are we compliant?** Every policy's writing agent is checked for ready-to-sell status and licensing in the policy's state.

It simulates the AI Deployment Specialist KPI "complete systems integration within 30 days of close" and the M&A Analyst skill "reconcile a carrier commission statement line by line." All data is synthetic.

## Users and what each needs to see

| User | Needs to see | Where |
|---|---|---|
| Agency owner or acquirer | One answer: can this agency go live, and if not, why not | Dashboard Overview, report.html |
| Integration specialist (the person doing the onboarding) | Every problem, its severity, the exact source row, and how to fix it, in priority order | Exceptions page, exceptions.jsonl |
| Finance or M&A analyst | Commission variances in dollars by carrier and agent, orphan payments, unpaid policies | Tie-out page, tie_out/*.json |
| Compliance lead | Which agents wrote business they were not ready to sell or licensed for | Agents page (RTS matrix) |
| Recruiter or hiring manager reading the repo | What problem this solves, how, and measured results, in under two minutes | README.md |

## Out of scope

- Real CRM, enrollment platform, or carrier API connectors. No credentials, no vendor formats claimed.
- Auth or user accounts on the dashboard. Editing data in the dashboard.
- PHI or any real data. No SSNs, ever (SSN-001 refuses them).
- Commission math beyond the fixtures rate table.
- The employee benefits line of business.
- Any LLM-written content in load files. Models answer bounded questions, they never write data.
- Fuzzy identity resolution (nicknames, typos, transposed dates). The generator injects these for bob-resolve, but this project only flags exact normalized name plus DOB collisions (DUP-002).

## Inputs (the four source shapes and their quirks)

Every agency drop is a folder (`drop/`) holding these files plus a `drop/manifest.json` with each file's expected row count. All four shapes are synthetic and generated in PR 3b.

| Source | Shape | Quirks the readers must handle |
|---|---|---|
| CRM export | AgencyBloc-style CSV, **one row per policy** with client fields repeated (2,600 rows for 2,000 clients in agency-a) | Non-UTF-8 encodings, odd delimiters, Excel serial dates arriving as text, inconsistent status words |
| Enrollment platform export | Sunfire-style CSV | Its own header names and date formats, MBIs, plan IDs |
| Carrier commission statements | XLSX, one per carrier, each with its own layout | Merged title row above the header, trailing total row (also used as the expected row count when no manifest exists), carrier-specific column names |
| Agent roster | Hand-kept spreadsheet with ready-to-sell (RTS) status per carrier, state, plan year, and line of business | Free-form headers, multi-value license state columns |

Readers keep raw values exactly as read. The one exception is cells openpyxl already returns as datetimes, which become ISO strings. Every row gets lineage at read time.

## Canonical schema reference

Full field table: `docs/schema.md` (written in PR 1a). Pydantic models live in `agency_schema`.

| Table | Key |
|---|---|
| clients | client_id |
| households | household_id |
| agents | npn |
| rts | (npn, carrier, state, plan_year, line_of_business) |
| policies | policy_id |
| commission_lines | (carrier, statement_period, line_no) |

Every row carries `Lineage`: source_file, sheet, row_number, raw_hash, run_id, mapping_version. Every stage reports problems as `ExceptionRecord` (never a class named `Exception`). Enums: LineOfBusiness {MA, PDP, MEDSUPP, ACA}, PolicyStatus {ACTIVE, PENDING, TERMINATED, CANCELLED, UNKNOWN}, CommissionType {NEW, RENEWAL, OVERRIDE, CHARGEBACK}, EligibilityReason {AGE, DISABILITY, ESRD}. Carrier is an open string normalized by dictionary, then Jev. Format rules (MBI, NPN, Medicare plan ID, Medigap letter, HIOS ID, ZIP, state) are pure functions in `agency_schema.formats`, specified in BUILD-GUIDE section 1.4 and tested with Hypothesis.

## Rule catalog reference

Full catalog: `docs/rules.md`, generated from the rule registry (registry skeleton in PR 1a, generator in PR 8). The source of the 46 rules is BUILD-GUIDE section 6 until docs/rules.md exists. Rule IDs are stable.

| Family | Rules | What it covers |
|---|---|---|
| ING | 4 | File reading: encoding, header row, trailing rows, delimiter |
| MAP | 3 | Column mapping |
| SSN | 1 | SSN refusal (raw gate) |
| CMP | 2 | Completeness (raw gate) |
| DOB, MBI, NPN, PLN, ADR, CON, DAT, STA | 22 | Row-level field checks |
| DUP, REF, RTS, LIC | 7 | Cross-record checks |
| TIE | 6 | Three-way tie-out |
| PII | 1 | Free-text privacy gate |

Totals by severity: 3 blockers, 21 errors, 17 warnings, 5 info.

**Blocking policy.** There are exactly three blockers: MAP-003 (a required field is missing after mapping), CMP-001 (rows received differ from rows expected), and SSN-001 (an SSN column is present). A blocker sets status FAILED and stops `clean/` from being written. **Errors** keep their rows out of `clean/`, but the run can finish PASSED_WITH_WARNINGS. **Warnings** pass through with a flag column. **Info** is logged only. RTS-001 is deliberately an error, not a blocker: almost every acquired agency has a few RTS gaps, and the run must still produce a load file with those policies excluded and surfaced.

SSN-001 and CMP-001/CMP-002 run on raw frames right after reading, before mapping and before any Jev call. A missing source is CMP-002 (warning), and the tie-out leg that needs it is marked NOT_RUN.

## Jev usage

Jev (TypeSafe) answers exactly four bounded questions. It never changes a rule verdict or a severity. Models fill gaps and order queues, rules decide.

| # | Question | Jev type | Used for | Thresholds (config.py) |
|---|---|---|---|---|
| 1 | Which canonical field does this header hold? | choice | Column mapping, after synonyms miss | At or above 0.85 auto-maps. 0.60 to 0.85 maps and raises MAP-002. Below 0.60 stays unmapped (MAP-001) |
| 2 | Which enum value does this messy value mean? | choice | Status, line of business, carrier names | At or above 0.85 maps, else UNKNOWN plus STA-001 |
| 3 | Is this exception a data-entry error or a real business event, and how much does it matter? | noul plus score | Triage lane and queue order | Entry error at or above 0.80, business event at or below 0.20, otherwise human |
| 4 | Does this free text contain personal health or identity details? | noul | PII gate, after a regex pre-filter | At or above 0.50 redacts |

**Modes.** `replay` is the default everywhere, including CI and the Stop hook, and reads recorded answers (cassettes) keyed by request hash. A cassette miss fails the test and prints the hash. `off` sends all four questions to the human queue, and the pipeline must still complete. `live` and `record` spend money: each use needs Alex's explicit approval, every time.

**Spend cap.** A hard budget guard stops any run at **$0.50** of estimated Jev spend. The manifest records actual calls and tokens so the estimate can be checked.

**Recording.** A cassette is keyed by a hash of the exact request, so it must be recorded against the requests the real pipeline sends. Header and enum cassettes are recorded in PR 7, against the PR 3b source files. Triage and PII cassettes are recorded in PR 12, once the full pipeline exists, never against the PR 3a canonical copy, or every cassette would miss. Each recording needs Alex's approval of the spend first.

**Deduplication.** Identical triage requests (same rule, value shape, and neighbors) are sent once per run and the answer is reused. The same goes for identical PII texts. Without this, a run could make more than 1,000 calls and commit more than 1,000 cassette files. PR 11 states the expected call count for agency-a, and PR 12's recording must match it.

**Minimization.** Jev receives minimized fields only. Mapping samples skip free-text-looking columns and anything matching a 9-digit pattern. Notes never reach any model before the PII gate.

**To be verified in PR 6, not assumed:** the API shape (`POST https://api.typesafe.ai/v1/systemone`, BUILD-GUIDE section 8) and the price ($0.042 per million input tokens, output free). PR 6 checks `docs.typesafe.ai` first and wraps an official SDK if a stable one exists. Alex has a key, kept in `.env` only.

## Three-way tie-out definition

Built as DuckDB SQL views in `engine/src/intake/tieout/sql/*.sql`. Tolerances live in `config.py`.

**Matching key**, in order: carrier plus carrier_member_id, then policy_ref, then normalized name plus DOB. A name plus DOB match is a weak match and raises TIE-006 (info).

| Leg | Compares | Proves | Variance code |
|---|---|---|---|
| A | Book vs statement | Every active policy in the period has a commission line | TIE-001 (warning): active policy unpaid |
| B | Statement vs book | Every commission line matches a policy in the book | TIE-002 (error): orphan payment, counted as unexplained revenue |
| C | CRM vs statement | CRM status agrees with the carrier | TIE-004 (warning): status disagreement |

**Dollar checks.** Each statement amount vs the expected amount from the fixtures rate table, within 1 percent or $1, whichever is larger (else TIE-003, warning). Totals by carrier and by agent within 0.5 percent (else TIE-005, error).

A leg whose source is missing is NOT_RUN, never silently passed. Each leg reports its status (RAN or NOT_RUN), matched count, variance count, and variance dollars.

## Run outputs

`runs/<run_id>/`, immutable. An existing run_id is refused unless `--overwrite` is passed. `--now <iso>` freezes the clock so demo output and screenshots do not churn.

| File | Purpose | Read by dashboard |
|---|---|---|
| manifest.json | run_id, timings, engine version, input files with sha256 and row counts, Jev mode and usage (calls, tokens, estimated cost), thresholds, status PASSED, PASSED_WITH_WARNINGS, or FAILED | yes |
| scorecard.json | Rows in, mapped, and clean; exceptions by severity and rule; tie-out totals and variances; detection summary against ground truth when present | yes |
| mapping/<source>.yaml | Learned header to field map with method (synonym, jev, human) and confidence, reused next run | no |
| exceptions.jsonl | One ExceptionRecord per line, with lineage, minimized value, suggested fix, blocks_load, lane, and Jev fields when present | yes |
| tie_out/*.json | Legs A, B, C, variances, totals by carrier, totals by agent | yes |
| rts_coverage.json | One cell per agent, carrier, state, and plan year: RTS held and used, held but unused, or used without RTS (the RTS-001 gaps). Feeds the Agents page matrix | yes |
| clean/ | Load-ready CSV and Parquet per table. Not written when FAILED | no |
| report.html | Self-contained static report with the same numbers as the dashboard | no |

**Sample-run contract (PR 1b).** Before the engine exists, the dashboard builds against hand-written sample runs that match the output models in `agency_schema`:
- `fixtures/sample-run/`: PASSED_WITH_WARNINGS, with exceptions at error, warning, and info severity across several rule families, all three tie-out legs RAN, and named cases from examples 3 and 4.
- `fixtures/sample-run-failed/`: FAILED on CMP-001, with expected vs received counts. A raw-gate failure stops before mapping, so all three tie-out legs are NOT_RUN, `rts_coverage.json` is empty, and there is no `clean/`.
- `fixtures/sample-run-passed/`: PASSED, zero exceptions above info.

Each contains manifest.json, scorecard.json, exceptions.jsonl, tie_out/*.json, and rts_coverage.json. A PR 1b test validates every file against the models' JSON schema. In PR 12, the end-to-end test validates real run output against the same schema, so engine and dashboard cannot drift. PR 13 copies `fixtures/sample-run/` into `dashboard/public/demo-run/` so the dashboard and Vercel show it. After PR 12, `npm run demo` replaces it with the real demo run, and the samples stay as test fixtures.

## Dashboard pages and the one question each answers

Static-first Next.js 16 on Vercel. Reads JSON from `public/demo-run` (sample runs until PR 12). No API calls, no environment variables.

| Page | Question | PR |
|---|---|---|
| Overview | Can this agency go live? Status banner, rows in vs clean, blockers, tie-out variance in dollars and policies, RTS gaps, Jev calls and cost, run time. One screen, no scrolling at 1440 wide | 13 |
| Sources | Did we receive every file, and did each one read and map cleanly? | 14 |
| Exceptions | What needs fixing, in what order, and how? Filter by severity, rule, source. Lineage drawer per row | 14 |
| Tie-out | Does the money agree across book, statements, and CRM? | 15 |
| Agents | Did anyone write business they were not ready to sell or licensed for? RTS matrix from rts_coverage.json | 15 |
| Runs | What changed since the last run? Load your own run locally, no upload to any server | 16 |

## Six concrete examples

These become tests. Examples 5 and 6 must be blocked. The named records in examples 3 and 4 are **planted on purpose** by the PR 3a injectors on top of seed 42 and listed in `ground_truth.json`, so they exist in every regeneration. The PR 3b writers do the same for the truncation point (example 5) and the SSN values (example 6).

**Ground truth keys.** Every defect in `ground_truth.json` carries a stable record key (policy_id, client_id, npn, or carrier plus statement_period plus line_no), set in 3a. PR 3b adds the source file and row number where that record landed. Scoring matches exceptions to ground truth by record key, never by 3a row position, because 3a rows do not line up with the 3b files.

1. **Happy path with mess.** `fixtures/agency-a/drop` (seed 42, 2,000 clients, 2,600 policies, 25 agents, 6 carriers, 3 statement periods, default injectors). The run completes PASSED_WITH_WARNINGS. The scorecard matches ground truth within the tolerances in `tests/e2e/test_agency_a.py`: every scored defect class detected at recall at or above 0.95; false positives on clean rows at or below 0.5 percent; unscored identity defects reported but not gated. **Missing either target fails the test** (verify goes red), so the README's numbers are always true. The clean world (no injectors) produces zero exceptions above info.
2. **Column mapping with Jev.** The CRM export header `Mbr DOB` with Excel serial values maps to `dob` via synonyms; the header `Birth Dt (mm/dd/yy)` is not in the dictionary, Jev returns `dob` with confidence at or above 0.85 (replay cassette), values parse, zero DOB-001 exceptions on those rows.
3. **RTS error.** Policy P-00417 written by NPN 1884412 for carrier Harborline in TX for plan year 2026; the roster shows no RTS for that combination. RTS-001 fires as an error with suggested fix "obtain RTS or reassign writing agent," the policy is excluded from `clean/policies.csv`, the run still finishes PASSED_WITH_WARNINGS, and the dashboard Agents page shows the gap in the RTS matrix.
4. **Orphan payment.** Harborline statement period 2026-08 line 212 pays 61.05 for carrier_member_id HL-998213, which exists in no policy. TIE-002 fires with the amount; it appears in `tie_out/leg_statement_vs_book.json` and in totals as unexplained revenue.
5. **Must block, truncation.** `fixtures/agency-a-truncated/drop` is identical except the CRM CSV (one row per policy) ends at row 2,574 of 2,600 while `drop/manifest.json` still says 2,600. CMP-001 fires on the raw frame before any mapping or Jev call, status FAILED, `clean/` is not written, `report.html` and the dashboard show a red banner with the expected versus received counts.
6. **Must block, SSN.** `fixtures/agency-a-ssn/drop` adds a column `SSN` to the roster. SSN-001 fires on the raw frame before any model call, status FAILED, and the column's values never appear in any log, exception, or output. The test reads the injected SSN values from `ground_truth.json` and greps the whole run directory for each one, expecting zero hits (a generic 9-digit grep would false-positive on hashes, NPNs, and phones).

## End-to-end check that proves it works

1. `npm run verify` is green locally and in CI on `main`, in Jev replay mode.
2. The clean world gives zero exceptions above info. The e2e tests run the full pipeline on all three fixtures: agency-a passes example 1's accuracy gates, agency-a-truncated and agency-a-ssn fail exactly as examples 5 and 6 describe, and every run directory validates against the output schema.
3. `npm run demo` regenerates `dashboard/public/demo-run` with a frozen clock, and the committed copy matches (no churn).
4. The Vercel production URL shows the Overview answering "Can this agency go live?" for the demo run, at 1440 and 375 wide, light and dark.
5. Every number in the README comes from the committed fixtures and the e2e scorecard, not from estimates.

## PR plan

Each PR is under 400 changed lines, excluding generated files (lockfiles, committed fixture data, generated docs). Lanes: **A** data pipeline, **B** Jev and rules, **C** dashboard. "Serial" PRs run alone. Merge in dependency order, lower number first when two are ready together. Each lane has one PR open at a time, and two lanes at once is the practical limit on this machine.

| PR | Name | Lane | Needs merged first | Main files | Est. lines | Tests | Done when |
|---|---|---|---|---|---|---|---|
| 0 | Scaffold | serial | none | everything in guide 2.2 | n/a (generated) | trivial | Done 2026-10-04: verify green, CI green, Vercel deploys |
| SPEC | Spec session (no code) | serial | 0 | SPEC.md, CHANGELOG.md | docs | none | This file merged |
| 1a | Canonical schema, formats, exception model, registry skeleton | serial | SPEC | agency_schema/models.py, enums.py, lineage.py, formats.py, exceptions.py (ExceptionRecord), registry.py, data/zip3_state.csv, docs/schema.md, intake/config.py skeleton (one commented section per PR, so lanes append without conflicts) | 360 | unit plus Hypothesis for MBI, NPN, plan IDs, ZIP; registry registers and lists | Format property tests pass; schema JSON exported; every later stage can emit ExceptionRecords |
| 1b | Output models and sample-run contract | serial | 1a | agency_schema/outputs.py (manifest, scorecard, tie-out, RTS coverage, run status), `intake schema` command (JSON schema plus `--ts` for dashboard/lib/types.ts), fixtures/sample-run/, sample-run-failed/, sample-run-passed/ | 300 | every sample file validates against the output JSON schema; all three statuses and all four severities present across the samples; `intake schema --ts` output is stable | Lane C can build every page from the samples |
| 2 | Synthetic clean world | A | 1a | synth_agency_data/world.py, rates.py, canonical_writer.py, cli.py; bump astral-sh/setup-uv in CI (ask first, `.github/` edit) | 380 | determinism by seed, referential integrity, RTS coverage complete | `synth generate` writes clean canonical CSVs plus an empty-defect ground_truth.json |
| 3a | Error injectors, planted cases, canonical-shape copy | A | 2 | synth_agency_data/injectors/*.py, planted.py (examples 3 and 4 records), canonical defected writer, ground truth with scored flags and a stable record key per defect | 340 | each injector yields labeled defects; planted records present by exact ID; every defect has a record key; ground truth round-trips | Rule PRs can test against the defected canonical copy |
| 3b | Source writers and fixtures | A | 3a | synth_agency_data/writers/*.py (four source shapes plus drop/manifest.json), docs/synthetic-data.md, fixtures/agency-a, -truncated, -ssn | 320 | writers reproduce each quirk; truncated CRM ends at row 2,574 of 2,600; SSN fixture values in ground truth; every defect gets its source file and row number, and the row it points to holds that record | Three fixture folders committed |
| 4 | Readers, ingest, raw gates | A | 1a, 3b | intake/readers/sniff.py, csv.py, xlsx.py, intake/ingest.py, intake/gates/refusal.py, completeness.py, reader constants in config.py | 400 | encoding, delimiter, header row, trailing totals, lineage; SSN-001; CMP-001, CMP-002 | All four fixture files read into raw frames with lineage; examples 5 and 6 pass at the gate level |
| 5 | Synonym mapping and store | A | 4 | intake/mapping/synonyms.py, store.py, data/synonyms.yaml, required fields in config.py, MAP-001 and MAP-003 | 300 | known headers map; unknown stay unmapped; yaml round-trips; MAP-003 fires | mapping/*.yaml written and reused |
| 6 | Jev client | B | 1a | jev_client/client.py, cassettes.py, cost.py, types.py, docs/jev.md | 320 | four modes, backoff on 429 and 529, cassette hit and miss, $0.50 budget guard trips | Replay works offline; live and record gated; API shape and price checked against docs.typesafe.ai |
| 7 | Jev mapping and enum normalization | A | 5, 6 | intake/mapping/jev_mapping.py, enums.py, thresholds in config.py, MAP-002 and STA-001, recorded cassettes (record mode, Alex approves the spend first) | 280 | thresholds route correctly; sample-value minimization; cassettes for fixture headers and values | Example 2 passes |
| 8 | Row validators | B | 1a, 3a | intake/rules/dob.py, ids.py, address.py, contact.py, dates.py, status.py, docs/rules.md generator | 400 | one positive and one negative test per rule, run on the 3a defected copy | Every DOB, MBI, NPN, PLN, ADR, CON, DAT rule fires on its planted defect |
| 9 | Cross-record checks | B | 1b, 3a | intake/checks/duplicates.py, references.py, rts.py (also builds rts_coverage), licenses.py | 320 | DUP, REF, RTS, LIC rules fire; clean world is silent; RTS coverage cells match ground truth | Example 3's RTS-001 fires on P-00417 (the clean/ exclusion is checked in PR 12) |
| 10 | Three-way tie-out | B | 1b, 3a | intake/tieout/load.py, views.py, variances.py, sql/*.sql | 380 | each leg finds injected variances; zero on clean world; tolerances; NOT_RUN when a source is missing | Example 4's TIE-002 fires with the amount and lands in the leg B output |
| 11 | Exceptions policy and triage | B | 6, 8 | intake/exceptions/policy.py, triage.py (with request deduplication), pii.py, a few hand-made test cassettes | 320 | blocking policy; Jev triage routes; PII gate redacts; identical requests are sent once; the expected agency-a call count is stated in the PR and in docs/jev.md | exceptions.jsonl complete with lineage, lanes, and fixes |
| 12 | Run orchestration, CLI, report | merge point | every PR from 1a to 11 (including 1b, 3a, 3b) | intake/run/*.py, report/html.py, templates, cli.py, recorded triage and PII cassettes (record mode, Alex approves the spend first) | 400 | replay finds a cassette for every call in all three fixture runs, and the call count matches PR 11's estimate; e2e on all three fixtures; output validates against the 1b schema; rules, checks, and tie-out on the PR 2 clean world give zero exceptions above info; manifest hashes; frozen clock; report renders | Examples 1, 5, 6 pass end to end; `npm run demo` works; tag v0.1.0 |
| 13 | Dashboard shell and Overview | C | 1b | app/layout (fix "Create Next App" title), (overview)/page, components/tiles, severity-badge, lib/run-loader, types, copy fixtures/sample-run into dashboard/public/demo-run | 380 | vitest for loader and tiles against the samples; Playwright shots | Overview answers "Can this agency go live?" at 1440 and 375 for all three samples |
| 14 | Dashboard Sources and Exceptions | C | 13 | app/sources, app/exceptions, components/tables, lineage-drawer | 400 | table filters; drawer shows lineage and fix | Exceptions filterable by severity, rule, source |
| 15 | Dashboard Tie-out and Agents | C | 13 (can run alongside 14) | app/tie-out, app/agents, rts-matrix | 380 | legs render, including NOT_RUN; variances table; RTS matrix | Examples 3 and 4 visible on the dashboard |
| 16 | Load your own run, run diff, dark mode, a11y | serial | 12, 15 | app/runs, lib/upload, intake diff command | 350 | client-side load; diff output; axe checks pass | A second run loads without network; `intake diff` prints changes |
| 17 | Header mapping benchmark | any free lane | 7 | bench/header_mapping.py, results.md generator | 250 | runs in replay; table has three rows | Results table in README |
| 18 | README, docs, screenshots, GIF, ADRs, release | serial | everything | README.md, docs/adr/0001 to 0005, docs/screenshots/*, CHANGELOG | 300 (mostly docs) | shots regenerate; links valid | v1.0.0 tagged, Vercel production shows the demo |

**Calendar** (two lanes at once; Alex reviews from Madrid until about Oct 20):

| Window | Work |
|---|---|
| Oct 6 to 12 | 1a, 1b (serial), then Lane A: 2, 3a, 3b; Lane B: 6 |
| Oct 13 to 19 | Lane A: 4, 5, 7; Lane B: 8, 9, 10, 11 |
| Oct 20 to 26 | 12 (merge point, tag v0.1.0) in one lane; Lane C: 13, then 14 and 15 one at a time, keeping to two lanes |
| Oct 27 to Nov 2 | 16, 17, 18, Fable sweep, tag v1.0.0 |

If a week slips, cut from the end (run diff, benchmark extras, extra dashboard views), never from tests, lineage, or the README. Leftovers from PR 0 are assigned above: the CI `setup-uv` bump goes in PR 2, and the dashboard title goes in PR 13. The first CI run after GitHub moves `ubuntu-latest` to Ubuntu 26 (Oct 19, 2026) gets checked by whichever lane owns it.
