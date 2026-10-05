# Changelog

One entry per PR.

## PR 0: Scaffold (2026-10-04)

- Repo layout per BUILD-GUIDE section 1.3. No feature code yet.
- Engine: Python 3.12 with uv. Four packages (agency_schema, synth_agency_data, jev_client, intake), ruff, mypy strict, pytest. Console scripts `intake` and `synth` with a placeholder `version` command.
- Dashboard: Next.js 16 (App Router, TypeScript, Tailwind), shadcn/ui, vitest, Playwright config.
- Root `npm run verify` runs every check. CI runs it on every push and PR.
- `.claude/settings.json` permissions and a Stop hook that runs verify before Claude can end a turn with uncommitted changes.
- Change from the build guide: Node is pinned to 24, not 20. Node 20 reached end of life on 2026-04-30.
- `typecheck` runs `next typegen` first, because Next 16 generates some page types at build time.

## SPEC: the contract for every PR (2026-10-04)

- SPEC.md written from the SPEC interview. It now overrides the build guide where they disagree.
- PR plan gains "Lane" and "Needs merged first" columns for running lanes in parallel.
- PR 1 splits into 1a (models) and 1b (sample runs that act as the engine-to-dashboard contract).
- PR 3 splits into 3a (defects, planted example records, a canonical-shape copy) and 3b (source files), so rule PRs can start before readers and mapping exist.
- New run output `rts_coverage.json` feeds the Agents page RTS matrix (the guide had no data source for it). `intake/config.py` skeleton moves to PR 1a so lanes don't both create it. PR 11 records the triage and PII cassettes.
- Second review: triage and PII cassettes recorded in PR 12 against real pipeline requests; PR 11 deduplicates triage calls and states the expected call count; ground truth uses stable record keys; PR 13 copies the sample run into dashboard/public/demo-run.
- Jev spend capped at $0.50 per run. Missing an accuracy target in the end-to-end test fails verify.

## PR 1a-i: Canonical models, exception model, registry skeleton (2026-10-04)

- PR 1a split into 1a-i (this PR) and 1a-ii (format functions and the ZIP table), because together they ran about twice the 400-line limit. 1a-ii runs alongside 1b. SPEC.md PR plan updated.
- `agency_schema`: the six table models, closed enums (Carrier stays open text), `Lineage`, `ExceptionRecord`, and `json_schema()`. No field has a default, unknown fields are refused, and Lineage is required on every table.
- Money (`monthly_premium`, `amount`) is an exact decimal to the cent, not a float, so tie-out tolerances do not drift.
- `minimize_value()` is the one shared masking function. ExceptionRecord refuses a `value_minimized` with three digits in a row, and refuses any blocker other than MAP-003, CMP-001, SSN-001.
- Fresh-eyes review fixes: value_minimized must have exactly the masked shape; short values keep at most a third of their characters; SSN-shaped text refused in message and suggested_fix; whole-number and yes/no fields refuse text; blank strings refused where `None` is meant; list fields are tuples.
- `/code-review` fixes: ExceptionRecord carries full `lineage` (SPEC: exceptions.jsonl rows have lineage), matching row_number and raw_hash; spaced SSNs refused in text too; the masked-shape check uses the same "at most a third" rule as minimize_value.
- Rule registry: `@rule`, `catalog()`, `run_rules()`. It applies the same identity checks and refuses duplicate ids.
- `intake/config.py` skeleton with one commented section per PR.
- New enum not named in the guide: `AgentStatus` (ACTIVE, INACTIVE, UNKNOWN) for the agents table.
- Guardrail checks left open by PR 0:
  - Stop hook: it fired but never ran the tests. Hooks run in a bare shell without nvm, so `npm` was not found and every stop with uncommitted changes was blocked regardless of test results. Fixed in `.claude/hooks/stop-verify.sh` (Alex approved): it adds `~/.local/bin` for uv, loads nvm and Node 24 when npm is missing, and blocks with a clear message if npm still cannot be found. Retested live: a deliberately broken test was blocked with the real failure shown.
  - Mid-string ask rule (`Bash(*--jev live*)`): `echo "--jev live"` ran without asking. Either the version matches prefixes only, or auto mode approved it. Protection falls back to `JEV_MODE=replay` in `.env`.

## PR 1a-ii: Format functions and ZIP table (2026-10-04)

- `agency_schema.formats`: MBI, NPN, Medicare plan ID, Medigap letter, and HIOS checks; ZIP prefix to state; phone, email, and name normalizers; `parse_date_loose`. Pure helpers that never raise. Models do not call them; PR 8's rules do.
- Two-digit years pivot at 1930 to 2029 (`05/01/29` is 2029). Excel serials from 20000 to 60000 are dates. Day-first slash dates are refused.
- `data/zip3_state.csv`: 939 rows covering the 50 states, DC, five Pacific territories, PR, VI, and AA, AE, AP. Built from USPS list L002 (2011, the newest readable copy). L002 names sorting facilities, so 32 prefixes were corrected by hand to the state the addresses are in (VA 201 among them). The planned second-source cross-check was dropped because no second list could be read reliably; docs/schema.md says so.
- Tests: Hypothesis for MBI, NPN, Medicare plan IDs, HIOS IDs, and every row of the ZIP table; the guide's invalid cases; every state present.

## PR 1b: Output models and sample-run contract (2026-10-04)

- `agency_schema.outputs`: Manifest, Scorecard, tie-out legs, variances, totals, RTS coverage, and the status enums (RunStatus, LegStatus, TieOutLeg, RtsCellState, JevMode). `RUN_FILE_MODELS` maps each run file to its model. Documented in the new `docs/outputs.md`.
- A tie-out leg that did not run has empty counts, not zeros, so a missing check can never look clean.
- Decisions with Alex: money is text in JSON and the dashboard formats it with one helper; Jev estimated cost keeps six decimals; tie-out variances show the full carrier_member_id; one PR despite running over 400 lines, because the extra is tests and docs.
- `intake schema --json` prints the JSON Schema (serialization mode, the shape of files as written). `intake schema --ts` writes `dashboard/lib/types.ts` with a small built-in generator. `json_schema()` now covers the output files and takes a mode.
- Three sample runs in `fixtures/`: sample-run (PASSED_WITH_WARNINGS, examples 3 and 4), sample-run-failed (CMP-001, all legs NOT_RUN), sample-run-passed. Written through the models with `minimize_value()` and a frozen clock.
- `agency_schema.run_dir.check_run_dir()` validates a whole run directory and checks that its files agree. PR 12 runs it on real output.
- Tests: every sample passes `check_run_dir` and round-trips byte for byte; all statuses and severities appear; each model rule refuses a file broken in exactly that way; the committed `types.ts` matches the generator.
- Review fixes (fresh-eyes subagent and `/code-review`): a PASSED run cannot have a leg that did not run; each TIE rule is tied to its leg; cross-file checks moved from the test into `check_run_dir`; Jev `off` makes no calls; RTS gaps list one exception per policy; duplicate totals rows and RTS cells refused; totals carry a not_run_reason; variance dollars cannot be negative; recall dropped (computed from detected and planted); sample messages no longer repeat raw values; the TS generator handles literals and non-string enums and refuses unknown shapes.
- Open question for PR 6 and PR 12: what the $0.50 budget guard does to a run (see the PR description).

## PR 2: Synthetic clean world (2026-10-04)

- `synth generate --seed 42 --clients 2000 --out ../fixtures/agency-a` writes six canonical CSVs under `canonical/` plus a `ground_truth.json` with no defects. Same seed, same bytes. Fixtures are committed in PR 3b, not here.
- Seed 42 gives 2,000 clients in 1,400 households, 25 agents (one top, four managers, twenty producers), 2,600 policies (MA 1,430, PDP 390, MEDSUPP 260, ACA 520), 3,740 RTS rows, and 6,651 commission lines for 2026-06 to 2026-08. About 1.4 MB.
- Six fictional carriers only. `rates.py` amounts are illustrative, not CMS maxima. Money is Decimal.
- The clean world is built to raise nothing above info: every value passes the 1a-ii format helpers, ZIPs come from the ZIP table for the client's state, age-based Medicare clients were 65 when their policy started, Medicare starts fall on the 1st, every writing agent is licensed and RTS for what they sold, every active policy is paid once per period at the rate-table amount, and no two clients share a normalized name and birth date.
- Choices to know: the world's "today" is 2026-10-01 (the demo clock). Policies start from 2022 on and each agent sells in two to four states, which keeps the RTS table small. CSVs carry no lineage columns, because SPEC adds lineage when a file is read. List fields are joined with "|".
- CI: `astral-sh/setup-uv` bumped from v6 to v10.2.0 (Alex approved), which runs on Node 24. From v10 on, setup-uv publishes only exact version tags, so a bare `@v10` does not resolve.
- Size: about 690 changed lines against a plan of 380, mostly because the formatter puts one field per line. Alex chose to ship it as one PR.

## PR 6: Jev client (2026-10-04)

- `jev_client`: typed requests and answers for noul, choice, and score; four modes (`replay` default, `off`, `live`, `record`); `off` and a tripped budget return a typed `Unresolved`; a replay miss raises `CassetteMiss` with the request hash.
- Cassettes hold the request body and response only, never headers, keyed by the public `request_hash` (sorted keys, fixed separators, SHA-256). `record` reuses an existing cassette instead of paying twice.
- Retries on 429 and 529 with doubling waits and jitter, 5 tries in all. 401, 422, and other errors raise at once with the body.
- `live` and `record` are refused unless the caller passes `allow_spend=True`.
- Usage per run: calls, tokens, estimated cost (six decimals), budget, and `budget_tripped`. `minimize_state` keeps allowlisted fields and drops notes before PII clearance; the client refuses notes too.
- API shape and price checked on docs.typesafe.ai on 2026-10-04 and written up in the new `docs/jev.md`. Price confirmed at $0.042 per million input tokens. The official `typesafe-sdk` exists but is not wrapped; no new dependency.
- Constants in the `# PR 6` section of `config.py`.
- SPEC change: the spend cap no longer "stops any run". A trip switches Jev to `off` for the rest of the run, the run completes, and remaining questions go to the human queue (decision made before this PR, following guide 7.6). The 1b `JevUsage` model is unchanged.
- SPEC: the 'to be verified' note on the API shape now records what PR 6 checked.

## PR 13: Dashboard shell and Overview (2026-10-04)

- The Overview answers "Can this agency go live?" for one run: a status banner (yes, yes with fixes, or no, with the engine's reason and any file whose row count came up short), tiles for blockers, errors, warnings, info, and clean rows, then tie-out differences in dollars, RTS gaps, Jev calls and estimated cost, and run time. A stacked bar shows exceptions by source file, with the counts written next to each bar.
- A check that did not run shows "Not checked", never 0. On the failed sample that covers errors, warnings, the tie-out, and RTS gaps, because the blocker stopped the run before those checks.
- `lib/money.ts` is the one money helper. It formats decimal text and adds amounts in whole cents with BigInt, so money never becomes a float. A lint rule refuses `parseFloat` anywhere in the dashboard.
- `lib/run-loader.ts` reads a run folder (manifest, scorecard, exceptions, RTS coverage) and checks its basic shape: same run in manifest and scorecard, known severities, money written as text. The page reads `public/demo-run` at build time, so the deployed site is static and makes no network calls.
- `public/demo-run` is a copy of `fixtures/sample-run` until PR 12's `npm run demo` replaces it.
- App shell: title "Agency Intake Kit" with a real description, a left nav at desktop width and a scrolling top bar on phones. Pages not built yet show as "(soon)" instead of links. Fonts: Inter, and the system mono face for ids.
- Dark mode follows the system setting. The manual toggle waits for PR 16.
- `npm run shots` writes `overview-<width>-<theme>.png` to `docs/screenshots` and checks the Overview fits one screen at 1440 by 900.

## PR 3a: Error injectors, planted cases, defected canonical copy (2026-10-04)

- `synth_agency_data/injectors/`: 25 injectors at the guide 7.3 default rates, grouped by what they touch (`clients.py`, `policies.py`, `commissions.py`, `roster.py`). Each is `(world, rng, rate) -> (world, defects)`, copies the rows it changes, and never mutates its input. 20 are scored; name typos, nicknames, DOB transposition, DOB month-day swap, and near-duplicate clients are unscored (`expected_rule_ids: []`, for bob-resolve).
- Every defect has a stable `record_key` (`policy_id`, `client_id`, or carrier plus statement_period plus line_no) and a `row_ref` into the defected CSV (row 1 is the header). A defected record is locked, so no record carries two defects.
- `planted.py`: SPEC example 3 (P-00417 is Harborline, TX, MA, plan year 2026, written by NPN 1884412, no RTS row) and example 4 (Harborline 2026-08 line 212 pays 61.05 to HL-998213, no policy). Supporting edits: producer `32227216` (agent06, Jeffery Wagner) is renamed to `1884412` everywhere and gets a TX license, P-00417 moves to TX client C-00452 (a 65+ PDP-only client), and line 212 is inserted so later lines shift down by one. Random injectors never touch the planted policy, its client, or line 212.
- `synth generate` now injects by default and writes `canonical-defected/` plus a filled `ground_truth.json`. `--no-inject` writes the clean world to `canonical/` with no defects. Planting needs seed 42 at 2,000 clients and says so if the world is too small.
- Committed `fixtures/agency-a/canonical-defected/` and `fixtures/agency-a/ground_truth.json` (793 defects, about 1.7 MB). A test regenerates them and fails if the bytes drift.
- PII in notes is left to PR 3b, which writes the CRM `Notes` column.
- Size: about 1,350 changed lines against a plan of 340, not counting fixture data. Shipped as one PR on the orchestrator's instruction.

## PR 14: Dashboard Sources and Exceptions (2026-10-04)

- Sources page answers "What did we receive, and did it read cleanly?" with one card per file: rows expected versus received, encoding, delimiter, header row, the reading and mapping checks that fired (ING, MAP, CMP, SSN rules), and a status (read cleanly, read with warnings, rows missing, or blocked the run). On the failed sample the CRM card shows 2,600 expected and 2,574 received.
- The run files do not record encoding, delimiter, or header row directly, so the page reads them from the ING rules: no ING-001 means UTF-8, no ING-002 means the header was on row 1, and spreadsheets need no delimiter.
- Exceptions page: a TanStack table (v9) with blockers first, then errors, warnings, and info; filters for severity, rule, and source that only offer values present in the run; counts by severity; a sticky header and a sticky first column for phones.
- Lineage drawer: select a row (click, Enter, or Space) to see the message, suggested fix, source file, sheet, row number, raw row hash, masked value, whether it blocks the load, and Jev scores as bars with the percent printed. Escape closes it. A notes value always shows as [redacted].
- The Overview banner links to the Exceptions page. The nav now links Sources and Exceptions and highlights only the current page.
- Not in this PR: the per-header mapping table (the dashboard does not read mapping/*.yaml), lane and scored filters, message search, copy as issue, and CSV export.

## PR 15: Dashboard Tie-out and Agents (2026-10-04)

- The Tie-out page answers "Does the money agree?" for one run: an answer banner, three cards for the checks (book vs statement, statement vs book, CRM vs statement) with matched, unmatched, weak-match counts and dollars, a table of every difference (member id, where, amount, rule, and the engine's explanation), and totals by carrier and by agent with an "All" row.
- A check that did not run shows "Not checked" and the engine's reason, never zeros. On the failed sample all three cards and both totals say "Not checked" and no table appears.
- Differences carry a direction word ("$61.05 more paid", "$31.00 less paid", "Even"), so the sign never depends on color. Totals rows are added with the BigInt helper in `lib/money.ts`.
- The Agents page answers "Is every writing agent allowed to sell what they sold?": an answer banner, the RTS gaps to fix (exception id, source file and row, message, suggested fix), a writing agents table, and the RTS matrix (agents by carrier, state, and plan year). Each cell says held and used, held but unused, or used without RTS, with an icon and a policy count; used without RTS cells are outlined and shaded.
- Example 3 (NPN 1884412, Harborline TX 2026, EX-000005, crm_export.csv row 419) and example 4 (Harborline 2026-08 line 212, HL-998213, $61.05, TIE-002) are visible on the pages and asserted in tests.
- `lib/tie-out.ts` reads `tie_out/*.json` and refuses money written as a number. `lib/agents.ts` shapes `rts_coverage.json` into the matrix.
- The Tie-out and Agents nav items are now links, using the `NavLink` component from PR 14. A test checks that only the page you are on is marked current.

## Screenshots and design notes (2026-10-04)

- `npm run shots` now captures all five pages at 1440 by 900 in light mode, plus the Overview at 375 wide and in dark mode, into `docs/screenshots/` with stable names: `overview-1440.png`, `overview-375.png`, `overview-dark.png`, `sources-1440.png`, `exceptions-1440.png`, `tie-out-1440.png`, `agents-1440.png`.
- Animations are off and reduced motion is on, so two runs write byte-identical images from the frozen demo run.
- The shots run also checks that the Overview fits one 1440 by 900 screen and that no page scrolls sideways at 1440 or 375.
- New `docs/design.md`: the tokens, severity colors and their meanings, type scale, layout, the one question each page answers, and how to regenerate the screenshots.
- No page code changed. The screenshots showed no visual bugs.

## PR 18a: ADRs and README draft (2026-10-04)

- First half of PR 18, written early. Docs only, no code.
- `docs/adr/0001` to `0005` plus an index: DuckDB SQL for the tie-out, Jev as a gate not a judge, static-first dashboard, synthetic data only, separate repos per project with `agency-data-commons` extracted later. Each records context, decision, and consequences, and cites the CHANGELOG entry behind it.
- ADR 0005 records a known gap: `jev_client` imports its constants from `intake/config.py`, so they must move before the package is extracted.
- README.md rewritten as a two-minute read for a non-engineer: what it is, who it is for, the five dashboard questions, what is synthetic and why, the data trust rules, how to run it, and a status list that names every PR not shipped yet. It publishes no detection rates or benchmark numbers, because the pipeline that measures them is not built. After merging main, the README embeds the four 1440-wide screenshots from `docs/screenshots/`.
- Still open for the rest of PR 18: the GIF, results tables, architecture diagram, link checker, v1.0.0 release.

## PR 8: Row validators (2026-10-04)

- `intake/rules/`: the 22 row rules from guide section 6, registered with `@rule`: DOB-001 to 003, MBI-001 to 003, NPN-001 and 002, PLN-001 to 004, ADR-001 to 003, CON-001 and 002, DAT-001 to 004, STA-001. Each rule is pure, never calls Jev, and builds its ExceptionRecord in one place (`frames.hit`), which passes every shown value through `minimize_value`. Messages carry minimized values only; policy ids and two-letter state codes appear as is.
- Rules read one of two frames (`frames.py`): the client frame, and the policy frame, which carries the client's DOB, MBI, and row lineage plus whether the writing agent is in the roster. The run date (`as_of`) is a column, so rules never read the clock.
- On the 3a defected copy every planted DOB, MBI, NPN, PLN, ADR, CON, DAT, and STA defect is detected on its exact row, with no extra hits except MBI-003 (one per Medicare policy of the client, as 3a planned). On the PR 2 clean world nothing above info fires.
- Choices: blank values are left to the completeness rules; a malformed NPN raises NPN-001 only, not NPN-002 too; DAT-001 also covers an unparseable termination date; MBI-002 and MBI-003 point at the client row, where the MBI lives; STA-001 accepts the five status words in any case and spacing.
- `uv run intake rules --md` prints the Markdown catalog; `docs/rules.md` is generated from it, and a test fails if the committed file drifts.
- `intake/rules/_canonical_io.py` is a temporary test loader for canonical CSVs, replaced by PR 4's readers.
- Thresholds in the `# PR 8` section of `config.py`: DOB_MIN_AGE, DOB_MAX_AGE, MEDICARE_AGE.

## PR 9: Cross-record checks and RTS coverage (2026-10-04)

- `intake/checks/`: seven rules, none of them blockers. `duplicates.py` has DUP-001 (exact duplicate row, by raw_hash, on every table), DUP-002 (same normalized name and DOB on two or more client ids, with the group id in the message), and DUP-003 (a policy id repeated with different content). `references.py` has REF-001 (policy points at a missing client). `rts.py` has RTS-001 (no ready-to-sell row) and RTS-002 (the row exists but ended before the policy took effect). `licenses.py` has LIC-001 (policy state not in the agent's licenses).
- RTS joins on agent, carrier, state (the client's address state when the policy has none), plan year (the effective year), and line of business, all trimmed and case-normalized. An ended RTS row gives RTS-002, never RTS-001. Agents missing from the roster are left to NPN-001 and NPN-002, so RTS and LIC skip them.
- `rts.build_rts_coverage` writes one cell per agent, carrier, state, and plan year: held and used, held but unused, or used without RTS (listing its RTS-001 ids).
- `_canonical_io.py` is a small canonical CSV loader for tests until PR 4's readers replace it.
- Against `fixtures/agency-a`, every planted DUP, REF, RTS, and LIC defect is found, and the clean seed-42 world gives no exceptions. Example 3 fires RTS-001 on P-00417.

## PR 10: Three-way tie-out in DuckDB (2026-10-04)

- `intake/tieout/sql/01` to `07`: the tie-out as commented DuckDB views. Lines match the book on carrier plus carrier_member_id, then policy_ref, then name plus DOB (a weak match, TIE-006). Leg A finds active policies with no line in a period (TIE-001), leg B finds orphan payments (TIE-002), leg C finds paid policies the CRM does not show as ACTIVE (TIE-004). Dollar checks: each line vs the rate table within the larger of $1 or 1 percent (TIE-003), carrier and agent totals within 0.5 percent (TIE-005). Money is DECIMAL(12,2) in SQL and Decimal in Python, never a float.
- `load.py` hands polars frames to DuckDB through the Arrow stream interface, so no pyarrow dependency. `views.py` runs the SQL files in name order. `variances.py` builds the six `tie_out/*.json` models and one TIE ExceptionRecord per finding.
- A missing commission or policy source makes every leg and both totals NOT_RUN with a reason and no counts.
- `_canonical_io.py` is a small private canonical CSV reader that PR 4's readers replace.
- `config.py` PR 10 section: `TIE_LINE_TOLERANCE_USD`, `TIE_LINE_TOLERANCE_PCT`, `TIE_TOTAL_TOLERANCE_PCT`.
- On agency-a every planted TIE-001 to TIE-004 defect is found with no extras. The clean world has zero variances and totals tie to the cent. TIE-005 fires on the defected world as expected.

## PR 3b: Source writers and fixtures (2026-10-04)

- `synth_agency_data/writers/`: the four messy source shapes plus `drop/manifest.json`. `crm_export.csv` (latin-1 with a byte order mark, Excel serial birth dates, three rotating date styles, mixed-case status words, Notes), `enrollment_export.csv` (semicolons, "Birth Dt (mm/dd/yy)", two-digit years), one `commissions_<carrier>.xlsx` per carrier (merged title row, header on row 3, trailing total row, three header layouts), and `agent_roster.xlsx` (Agents and RTS sheets, comma license lists). Spreadsheets are saved with frozen timestamps, so the bytes never churn.
- `synth generate` now writes `drop/` too, and takes `--truncate-crm N`, `--add-ssn-column`, and `--no-canonical`.
- PII in notes: 26 obviously fake sentences (1 percent of CRM policy rows) in the CRM Notes column, recorded as `pii_in_notes` (PII-001, scored) keyed by `policy_id`.
- Every ground truth defect now also says where it landed: `source_file`, `sheet`, `source_row`. A test opens each file and checks the row holds that record.
- Fixtures committed: `fixtures/agency-a` (adds `drop/`; `canonical-defected/` unchanged), `fixtures/agency-a-truncated` (CRM keeps 2,574 data rows, manifest says 2,680, plus a `truncated_file` CMP-001 defect), `fixtures/agency-a-ssn` (roster SSN column, values all in never-issued area 000, listed in ground truth). A test regenerates all three and fails on any byte change.
- SPEC and CLAUDE.md: the CRM export has 2,680 rows, not 2,600: 2,600 policies, 34 planted duplicate rows, and 46 clients with no policy (40 re-keyed copies plus 6 whose only policy was orphaned), each on a row with the policy columns blank. Example 5 now reads 2,574 of 2,680.
- New `docs/synthetic-data.md`: every injector, rate, scored flag, file quirk, and fixture.

## README: why this exists, status refresh (2026-10-04)

- New "Why this exists" section written for the recruiting reader: who built it, what it demonstrates, and how AI coding agents were used under the spec. Status lists updated for PRs 8, 9, 10.

## PR 4: Readers, ingest, and raw gates (2026-10-04)

- `intake/readers/`: `sniff.py` (encoding, delimiter, header row, trailing total rows), `csv.py`, and `xlsx.py`. Every source file or sheet becomes a `RawTable`: a polars frame with each source column under its header exactly as read (all text, blank is null) plus a `lineage` struct column with the six `Lineage` fields. `raw_hash` is the sha256 of the row's raw cells joined by the unit separator, the same recipe the PR 8 and PR 9 test loaders use.
- Encoding: a UTF-8 byte order mark is stripped but not trusted. The body is tried as strict UTF-8, then latin-1, so the CRM export (marker plus latin-1 text) reads with its accents intact. charset-normalizer is not used: on that file it guessed cp1250, which turns "ñ" into "ń".
- Header row: the first row where at least 60 percent of cells are words, so the merged title and subtitle rows of the commission statements are skipped and the header is found on row 3. Trailing "Total" and blank rows are dropped and counted; a total row's printed line count is kept as the fallback expected count.
- xlsx: values only. Real date cells become ISO strings (a bare date at midnight); text such as "45901" stays text.
- ING-001 (not UTF-8), ING-002 (header not on row 1), ING-003 (trailing rows dropped) are info; ING-004 (delimiter guessed with low confidence) is a warning.
- `intake/ingest.py` reads a drop folder by `drop/manifest.json` (or every csv and xlsx file when there is none) into an `IngestResult`.
- `intake/gates/refusal.py`: SSN-001 blocks when a header says SSN or social, or 90 percent of a column's values look like SSNs. The record names the column only; no value is copied, counted, or masked.
- `intake/gates/completeness.py`: CMP-001 blocks when rows received differ from the manifest (else the total row). CMP-002 warns when a listed file or sheet is missing and names the tie-out legs that cannot run.
- Examples 5 and 6 pass at the gate level: the truncated fixture gives CMP-001 expected 2,680, received 2,574; the ssn fixture gives one SSN-001 and none of its 25 values appears in any record. Ground truth rows point at reader rows holding the record key.
- `config.py` PR 4 section: reader encodings, delimiters, header and total-row settings, `RAW_MAPPING_VERSION`, and the SSN gate settings.

## Jev client review fixes

- #22: a reply is counted toward the $0.50 budget before it is checked, so a billed reply that fails validation (or has a broken usage block, or is not JSON) still counts. In `record`, the raw reply is saved as a cassette before the check and the error names the file, so a retry does not pay again. New `JevBadReply` error (a `ValueError`).
- #23: a choice answer must pick an offered option and its probabilities may only name offered options. A score must sit between level 0 and the top level, with probabilities keyed only by offered level numbers. Anything else is rejected with `JevBadReply`.
- #24: `JevHTTPError` text no longer includes the raw body. The key, its first 8 characters, and any `Bearer ...` text become `[redacted]`, and the excerpt is cut at 200 characters.
- #25: `live` always calls the API and never reads cassettes. Only `replay` and `record` read them. docs/jev.md says so.

## Dashboard review fixes (2026-10-04)

- #11: The Tie-out answer and the Overview tile now count the same differences the table lists. Checks that belong to no leg (TIE-003 rate table, TIE-005 totals) are named separately: "Not fully. 4 differences to review." and "$85.55 in differences across 3 of 3 checks, plus 1 commission off the rate table or totals ($6.50)." A status disagreement (TIE-004) shows "Status only, no amount" instead of "Even" and "Paid nothing, expected nothing".
- #12: On a FAILED run the Errors, Warnings, and Info tiles show counts found before the run stopped, with the context "Found before the run stopped. Row checks did not run." They say "Not checked" only when the count is 0.
- #15: The tie-out loader refuses a leg file that holds the wrong leg, a leg that ran with a count missing, a leg that did not run but has numbers, and leg files that disagree with the run's scorecard. A leg card shows "Not reported", never 0, for a missing count.
- #14: A broken run file now names itself: "manifest.json: not valid JSON (...)", "exceptions.jsonl line 3: not valid JSON (...)", "tie_out/variances.json: not valid JSON (...)".
- #16: The lineage drawer acts as a real modal. The page behind it is inert, Tab and Shift+Tab stay inside it, and focus returns to the row you opened it from when it closes.
- #13: On a FAILED run, files without their own problem show "Read, not mapped (run stopped)" and "Mapping not checked. The run stopped first." The Sources header counts files read and says mapping was not checked.

## PR 11: exceptions policy, triage, PII gate (2026-10-04)

- `intake/exceptions/policy.py`: the run status (any of the three blockers MAP-003, CMP-001, SSN-001 means FAILED; any error or warning means PASSED_WITH_WARNINGS; otherwise PASSED), the rows errors keep out of `clean/`, catalog suggested fixes for stages that left one blank, and the lanes triage does not decide (blockers to REVIEW, info stays UNREVIEWED).
- `intake/exceptions/triage.py`: Jev question 3 for every error and warning. The state is the rule, field, value shape, and a few neighbor fields per family (in `config.py`), never raw values or notes. 0.80 or more goes to SUGGESTED_FIX, 0.20 or less to BUSINESS_EVENT, in between to REVIEW, and no answer (off mode or the spend guard) to UNREVIEWED. Identical requests are sent once, keyed by the public request hash. `queue_order` sorts the fix-first queue deterministically.
- `intake/exceptions/pii.py`: the PII gate. A regex pre-filter picks notes worth a look, SSN-shaped text and 9 to 11 digit numbers are redacted with no call, other flagged text goes to Jev with digits masked, and 0.50 or more redacts to `[redacted]` and raises PII-001. With no answer the gate redacts (fails closed). PII-001 joins the rule catalog and `docs/rules.md`.
- Expected Jev calls for fixtures/agency-a today: 105 triage calls for 354 row-rule and cross-record exceptions (354 calls without deduplication), 0 PII calls. Asserted in tests and explained in `docs/jev.md`.
- Hand-made, clearly synthetic cassettes in `engine/tests/cassettes/synthetic/` (3 files). The pipeline never reads that folder. No Jev spend: every test uses replay or httpx.MockTransport.

## PR 5: Synonym mapping and the mapping store (2026-10-04)

- `intake/mapping/synonyms.py`: `normalize_header` is the one normalization for headers and synonyms alike (accents and punctuation dropped, camelCase split, "#" read as "number", abbreviations such as dt, eff, mbr, no, yr expanded). Only an exact match after normalizing maps; a near match is offered as a candidate and never mapped on its own.
- `intake/data/synonyms.yaml`: the synonym table, by canonical table and field. 77 of the 79 fixture headers map. Two stay unmapped for Jev in PR 7: "Birth Dt (mm/dd/yy)" (SPEC example 2) and the Northwind and Cardinal "Paid" column (a date or an amount; the values decide). A spelling that means two fields of one table is refused when the file loads.
- `intake/mapping/store.py`: `mapping/<key>.yaml` beside `drop/`, one per source (the roster gets `roster_agents` and `roster_rts`), with header, table, field, method, confidence, and decided_at. A stored decision wins over the synonym table; a person can set `method: manual`, or leave the field empty to ignore a column. Writing what was read gives the same bytes, so a second run leaves the file unchanged.
- `intake/mapping/headers.py`: `map_table` maps a raw table, saves its mapping, and returns a mapping version for lineage. MAP-001 (warning) names each unmapped header with its closest fields; a second column for a field already mapped is also MAP-001. MAP-003 (blocker) fires once per required field with no mapped column. A combined name column ("Client Name", "Agent Name") covers first and last name. Enrollment is not checked for MAP-003, because it cross-checks the CRM and loads no table of its own.
- `config.py` PR 5 section: required fields per table, the CRM client id carried into policies, and how close a header must be to be offered as a candidate.
- fixtures/agency-a maps with three MAP-001 warnings and no MAP-003.

## SSN gate hardening (#39, #51)

- SSN-001 no longer blocks a run on a column of nine-digit NPNs. The gate now weighs the header and the value shape together: a header naming an SSN (SSN, Social, Soc Sec, Tax ID, TIN) always blocks; a header naming a known id field (NPN, MBI, policy, member, phone, ZIP, plan ids) never blocks on values alone; dashed or spaced SSN text in at least 1 percent of cells blocks, free text included; bare nine digits block only in 90 percent of cells and only when some value cannot be an NPN.
- The output is unchanged: one file-level blocker record per column, and no value is ever echoed. The decision rule is in `intake/gates/refusal.py` and docs/schema.md; the word lists and shares are in the PR 4 section of `config.py`.
- #39: a header the PR 5 synonym table maps to an id field (npn, mbi, policy id, member id, phone, zip, plan id) also counts as a known id header.
- #51: when a file has no header row, an SSN in the first row became the column name and the message printed it in full. A header that looks like an SSN (dashed, spaced, or nine or more digits) is now masked with `minimize_value` and labeled "header value masked"; the message names the column by position.
- New tests in `engine/tests/unit/test_ssn_gate.py`, including a headerless file in dashed, spaced, and bare forms.

## PR 16: Load your own run, run diff, dark mode, accessibility (2026-10-04)

- Runs page: pick a run folder's files (or drop the folder) and every page shows that run, with a banner naming it and a "Back to the demo run" button. The files are read in the tab only. Nothing is uploaded or stored, and a reload clears them. `lib/upload.ts` matches files by name, skips anything that is not a run file without reading it, and lists every problem by file ("scorecard.json: missing", "exceptions.jsonl line 2: not valid JSON", files from two runs).
- `lib/run-loader.ts` and `lib/tie-out.ts` now only parse text, so the browser can reuse them. Reading the demo run from disk moved to `lib/run-dir.ts`. Pages still render the demo run on the server; a small client wrapper swaps in a loaded run.
- Dark mode is a class on the page. An inline script applies the saved choice (or the system setting) before the first paint, and a header toggle switches it.
- `intake diff <run_a> <run_b>` prints the status change, exception counts by severity, new and resolved exceptions by rule, and each tie-out leg's dollar change.
- `fixtures/sample-run-partial`: two tie-out legs ran, CRM vs statement did not. `check_run_dir` covers it, and the Overview and Tie-out tests check "2 of 3 checks ran", the partial answer, and that the card that did not run shows "Not checked" with no numbers (#18).
- `e2e/a11y.spec.ts`: axe on every page in light and dark, with the lineage drawer open, and on a loaded run; every page at 375 wide in both schemes (#17). Run by hand; it needs the Playwright browser.
- Shared `PageHeader` now used by Overview, Sources, and Exceptions. Removed the unused `next-themes` and `recharts` packages and the dead "(soon)" nav branch (part of #19). Added `@axe-core/playwright` as a dev dependency.

## PII gate fix (#55)

- `intake/exceptions/pii.py`: a new regex layer finds identity shapes with no Jev call: SSN shapes, emails, phone numbers, dates of birth after a DOB label, card numbers, bank and routing numbers (8 to 17 digits, or labeled account, acct, routing, IBAN), driver's license numbers, Medicare and member ids, anything labeled SSN, social, password, or PIN, and a name after a relationship word. Each match is replaced in place by a typed placeholder such as `[REDACTED:phone]`, and PII-001 fires with `value_minimized` from `minimize_value` and the kinds in the message, never the raw value.
- Text that still holds a date, a drug-like word, or a health word goes to Jev's noul question, already redacted and with digits masked. At or above 0.50 the whole text is redacted; with no answer the gate still fails closed.
- `config.py`: `PII_RELATION_WORDS`, the relationship words that mark a following name.
- All 26 planted notes in fixtures/agency-a now raise PII-001 (before: 0), with 0 Jev calls; the 132 clean notes raise nothing. `docs/jev.md` describes both layers.
- Tests: `engine/tests/unit/test_pii_patterns.py` runs the gate over every fixture note and each shape, and checks no raw value reaches a record, a request, or a cassette. No Jev spend: off mode, replay, and httpx.MockTransport only.

## Reader and date review fixes (#50, #41)

- Readers find the trailing total block by content, not position. A first cell of Total, Totals, Total:, Grand total, Subtotal, or Sub-total (any case or spacing) starts it, and any blank or footer lines after it ("Generated by ...", "Page 1 of 1") are dropped with it and counted in ING-003. CMP-001 still compares the manifest count with received data rows only, so a Totals row plus a footer no longer blocks the run. A footer line with no total row above it is kept as data.
- `TOTAL_ROW_WORDS` in config.py is replaced by `TOTAL_ROW_PATTERN` and `FOOTER_MAX_FILLED_CELLS`.
- `parse_date_loose` reads compact yyyymmdd dates such as 20260501 (eight digits, year 1900 to 2099, a real month and day). Eight digits are never read as an Excel serial, so serials 20000 to 60000 still work. docs/schema.md documents the new shape. The enrollment export keeps writing compact dates so the quirk stays in the fixture, and a test parses all 1,847 of its effective dates.

## 3a review fixes: ground truth

- Issue 26: a DUP-002 collision now labels both clients. The original gets its own scored
  `name_dob_collision` defect (`copied_to` names the copy), so DUP-002 on the original's CRM rows
  is no longer a false positive. A PR 9 test checks DUP-002 fires on exactly the labeled clients.
- Issue 28: ground truth now expects TIE-005. After all injectors run, `total_variances` adds one
  `statement_total_variance` defect (scored, TIE-005) for each carrier or agent whose statement
  total is more than 0.5 percent off the book, computed from the injected amounts. Keys match
  tie-out's output: `{"carrier": ...}` or `{"agent_npn": ...}` (an orphan line with no agent is
  `(blank)`, as tie-out reports it). These have no canonical or source row, so `row_ref`,
  `source_file`, `sheet`, and `source_row` are null. Seed 42 breaches at 3 carriers (Bluepeak,
  Harborline, Summit Health Plans), not all 6 as the issue estimated, plus 45 agents. PR 10's
  test now requires its TIE-005 findings to equal ground truth exactly.
- Issue 29: example 3 (P-00417, NPN 1884412, Harborline, TX, 2026, no RTS, TX licensed) and
  example 4's line 212 are now checked after every injector runs and in the committed fixture.
- Issue 54: the CRM writer rotated date styles and status casing by row, so none of the 26
  exact duplicate rows was byte-identical in `crm_export.csv` and DUP-001 could not fire on the
  real drop (they all looked like DUP-003). An exact duplicate now repeats its original row's
  cells byte for byte; every other row keeps the rotation, and the 8 DUP-003 copies still
  differ. A test reads the real CRM file and checks all 26 pairs match and all 8 differ.
- Locking the DUP-002 originals changes which clients the near-duplicate injector copies, so
  `canonical-defected/clients.csv` and the CRM exports changed. No rule or check logic changed.
- Defect counts: agency-a 819 to 877 (scored 659 to 717; DUP-002 10 to 20; TIE-005 0 to 48).
  agency-a-truncated and agency-a-ssn 820 to 878. Regenerate with
  `uv run synth generate --seed 42 --out ../fixtures/agency-a`, then the same with
  `--truncate-crm 2574 --no-canonical` and `--add-ssn-column --no-canonical` for the other two.

## PR 17: header mapping benchmark

- `intake bench header-mapping` scores three approaches on 134 labeled headers: synonyms only, synonyms then Jev, synonyms then Sonnet. It runs in Jev replay by default and makes no network calls.
- The labeled set (`engine/src/intake/bench/data/header_labels.yaml`) holds all 79 distinct headers in the agency-a source files (a test checks the list against the files) and 55 synthetic variants, 11 of which hold no canonical field. Small and synthetic; the numbers describe this set only.
- Per approach: accuracy, coverage, wrong mappings, "not recorded", model calls, and estimated cost per 1,000 headers. A header with no Jev recording is "not recorded", in its own column, never counted as wrong or missed. When no Jev answers are recorded the row says "not measured" instead of a percentage that would really be the synonyms' score.
- Costs are estimates from token counts at stated prices (Jev $0.042 per million input tokens; Sonnet $2 in and $10 out per million). Latency is measured only for real network calls; replay says so.
- The Sonnet arm runs only with `ANTHROPIC_API_KEY` set and `--sonnet` passed. Without a key its row says "skipped: no key". Adds the `anthropic` SDK as a dependency (uv.lock changed).
- Writes `docs/benchmark-header-mapping.md` and the README table between `<!-- benchmark:start -->` and `<!-- benchmark:end -->`. Recording Jev answers later is one command, after Alex approves the spend: `uv run intake bench header-mapping --jev record --approve-spend`.
- `config.py` PR 17 section: the 0.60 cutoff the benchmark scores with, the Sonnet model id, and the Sonnet price.

## Checks and tie-out review fixes

- #53: The tie-out no longer matches statement lines by row number. Every row gets `_rec`, its position in its table, and that is the only row key the SQL joins on; lineage row numbers (which restart in each carrier file) are never used as keys in the checks or the tie-out. Six per-carrier statement files with overlapping row numbers now give exactly the ground truth (131 TIE-001, 68 TIE-002, 66 TIE-003, 40 TIE-004), and example 4 still lands in leg B.
- #42: RTS-001, RTS-002, and DUP-002 read every date through `parse_date_loose` (ISO, US, two-digit years, Excel serials). A policy RTS could not check for want of an effective date is counted in `CrossRecordResult.skipped` and logged; the date itself stays reported once, by DAT-001.
- #43: License states split on `|`, comma, semicolon, slash, or spaces through one shared splitter (`intake/normalize.py`, pattern `LIST_SPLIT_PATTERN` in `config.py`), so the roster's "FL, GA, TX" works.
- #44: The tie-out reads policy dates, client DOBs, statement DOBs, and statement periods once in Python (`tieout/prepare.py`) before DuckDB, so mixed date styles stay in leg A and the name plus DOB match works with serial and US dates. Unreadable values are counted in `TieOutResult.skipped` and logged.
- #45: Amounts go through one money normalizer (`parse_money`: `$`, commas, `(61.05)` as negative, spaces, Decimal out). A blank or non-numeric amount is one TIE-003 on that line with its lineage ("has a blank amount", "has an amount that is not a number"), never a crash or a silent drop.
- #47: A chargeback (CHARGEBACK type or a negative amount) on a policy that is CANCELLED, TERMINATED, or ended by the period raises no TIE-003 or TIE-004, and the book side of the totals expects it. On an active policy it still raises TIE-003. Chargebacks never count as the carrier paying in leg C. OVERRIDE lines are checked only against an OVERRIDE rate.
- #48: A carrier and period the book expected money for, with no statement, is a TIE-005 (error) "No <carrier> statement was received for <period>" carrying the expected dollars, and the carrier stays in the totals (paid 0). CMP-002's suggested fix for a missing statement now says what the tie-out does.
- #49: Tie-out and cross-record exceptions carry the row's own lineage from the reader (file, sheet, row, hash, run, mapping version), not `sheet: null` and `"canonical"`. Both stages accept reader frames with the `lineage` struct column.
