# Run outputs

The files in `runs/<run_id>/` that the dashboard and report read. Code: `engine/src/agency_schema/outputs.py`. `RUN_FILE_MODELS` maps each file to its model; `exceptions.jsonl` holds one `ExceptionRecord` per line (see `schema.md`).

## Ground rules

- Same as the tables: no defaults, unknown fields refused, blank means `None`.
- **Not measured is not zero.** A tie-out leg that did not run has its counts as `None` and a `not_run_reason`. A 0 would look like "checked, nothing wrong", so the model refuses a NOT_RUN leg with numbers.
- **Money is text in JSON** (`"61.05"`), so no cents are lost. The dashboard keeps it as a string and formats it with one helper (PR 13). Jev cost keeps six decimals, because a run costs fractions of a cent.
- Times carry a time zone. Sample runs use the frozen clock `2026-10-01T09:00:00Z`.

## Files

| File | Model | Holds |
|---|---|---|
| manifest.json | Manifest | run_id, start and finish times, engine version, status, `status_reason` (one sentence for the banner, required unless PASSED), input files (sha256, rows expected and received), Jev usage (mode, calls, tokens, estimated cost), thresholds used |
| scorecard.json | Scorecard | rows in, mapped, and clean; exception counts by severity and by rule; one tie-out summary per leg; RTS gap count; detection against ground truth per defect class, planted and detected (recall is detected divided by planted), or `None` |
| tie_out/leg_book_vs_statement.json | LegResult | Leg A summary and its TIE-001 variances |
| tie_out/leg_statement_vs_book.json | LegResult | Leg B summary and its TIE-002 variances (orphan payments) |
| tie_out/leg_crm_vs_statement.json | LegResult | Leg C summary and its TIE-004 variances |
| tie_out/variances.json | VarianceReport | every variance from every leg plus the dollar checks (TIE-003, TIE-005) |
| tie_out/totals_by_carrier.json, totals_by_agent.json | Totals | book expected vs statement paid per carrier or agent NPN, the difference, unexplained revenue, within tolerance; a `not_run_reason` when it did not run |
| rts_coverage.json | RtsCoverage | one cell per agent, carrier, state, and plan year |

## Status values

| Enum | Values |
|---|---|
| RunStatus | PASSED (zero exceptions above info), PASSED_WITH_WARNINGS (errors or warnings, no blocker), FAILED (at least one blocker, no clean rows) |
| LegStatus | RAN, NOT_RUN |
| TieOutLeg | BOOK_VS_STATEMENT (A), STATEMENT_VS_BOOK (B), CRM_VS_STATEMENT (C) |
| RtsCellState | HELD_AND_USED, HELD_UNUSED (no policies written), USED_WITHOUT_RTS (an RTS-001 gap; lists its exception ids) |
| JevMode | replay, off, live, record |

## Checks the models enforce

- Scorecard: rows only shrink (clean, then mapped, then in); counts by rule and by severity add up to the same total; exactly one summary per leg, in leg order; the status matches the severity counts; a run with a leg that did not run is never PASSED.
- Legs: a leg that ran has every count; `weak_matched` is the part of `matched` made on name plus DOB only; `variance_count` and `variance_dollars` (the sum of absolute differences) match its variances.
- Variances: each rule belongs to one leg (TIE-001 leg A, TIE-002 leg B, TIE-004 leg C; TIE-003 and TIE-005 to none). `difference` is paid minus expected, with a missing side counted as zero. The same goes for totals.
- RTS cells: only HELD_UNUSED has zero policies; a USED_WITHOUT_RTS cell lists one RTS-001 exception id per policy. Each agent, carrier, state, and year appears once, and so does each totals row.
- Jev mode `off` makes no calls.
- Variances carry the full `carrier_member_id`, so an analyst can chase a payment with the carrier. The matching ExceptionRecord shows it masked.

## Checking a whole run

`agency_schema.run_dir.check_run_dir(path)` validates every file and checks that they agree: manifest and scorecard share run_id and status; scorecard counts match `exceptions.jsonl`; scorecard leg summaries match the leg files; `variances.json` and the leg files list the same leg variances; every variance and RTS gap points at an exception with the right rule; each totals file is grouped the way its name says; a FAILED run has no `clean/`. The sample tests use it now, and the end-to-end tests run it on real output in PR 12.

## Sample runs (the contract)

`fixtures/sample-run/` (PASSED_WITH_WARNINGS, with examples 3 and 4), `fixtures/sample-run-failed/` (CMP-001, 2,600 expected and 2,574 received, all legs NOT_RUN, empty RTS coverage, no `clean/`), and `fixtures/sample-run-passed/` (PASSED, info only). Synthetic data. Tests run `check_run_dir` on each one and check that every file is byte-for-byte what the models write, so money can never sneak in as a number. Messages do not repeat raw values; the masked value is in `value_minimized` and amounts are in the tie-out files. When an output model changes, update the samples and regenerate the types.

## TypeScript for the dashboard

`cd engine && uv run intake schema --ts` writes `dashboard/lib/types.ts` from the JSON Schema in serialization mode (the shape of the files as written). `uv run intake schema --json` prints that schema. A test fails when the committed `types.ts` is out of date.
