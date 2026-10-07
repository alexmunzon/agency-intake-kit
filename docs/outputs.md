# Run outputs

The files in `runs/<run_id>/` that the dashboard and report read. Code: `engine/src/agency_schema/outputs.py`. `RUN_FILE_MODELS` maps each file to its model; `exceptions.jsonl` holds one `ExceptionRecord` per line (see `schema.md`).

## Ground rules

- Same as the tables: no defaults, unknown fields refused, blank means `None`.
- **Not measured is not zero.** A tie-out leg that did not run has its counts as `None` and a `not_run_reason`. A 0 would look like "checked, nothing wrong", so the model refuses a NOT_RUN leg with numbers.
- **Money is text in JSON** (`"61.05"`), so no cents are lost. The dashboard keeps it as a string and formats it with one helper (PR 13). Jev cost keeps six decimals, because a run costs fractions of a cent.
- Times carry a time zone. Sample runs use the frozen clock `2026-10-01T09:00:00Z`. When `as_of` is set the clock was frozen, so `started_at` and `finished_at` are not a measurement: the dashboard and report say "Run time: not measured (frozen clock)" instead of a duration.

## Files

| File | Model | Holds |
|---|---|---|
| manifest.json | Manifest | run_id, start and finish times, `as_of` (the frozen clock from `--as-of`, else null), engine version, status, `status_reason` (one sentence for the banner, required unless PASSED), input files (sha256, rows expected and received), Jev usage (mode, calls, tokens, estimated cost, `invalid_answers`: replies that did not fit the question and were not used), `budget_tripped` (the $0.50 spend cap was reached and Jev went off for the rest of the run; the mode stays the configured one), thresholds used |
| scorecard.json | Scorecard | rows in, mapped, and clean; exception counts by severity and by rule; one tie-out summary per leg; `rts_gaps`, the count of agent, carrier, state, and year cells used without RTS (the dashboard and report show policies instead, which is the RTS-001 count); detection against ground truth per defect class, planted and detected (recall is detected divided by planted), plus `clean_rows` (rows that hold no planted defect, the false positive denominator; not the same as `rows_clean`, the rows written to `clean/`), `false_positive_rows` (clean rows that got a blocker, error, or warning), and `false_positive_rate` (the one divided by the other, to 6 places), or `None` |
| tie_out/leg_book_vs_statement.json | LegResult | Leg A summary and its TIE-001 variances |
| tie_out/leg_statement_vs_book.json | LegResult | Leg B summary and its TIE-002 variances (orphan payments) |
| tie_out/leg_crm_vs_statement.json | LegResult | Leg C summary and its TIE-004 variances |
| tie_out/variances.json | VarianceReport | every variance from every leg plus the dollar checks (TIE-003, TIE-005) |
| tie_out/totals_by_carrier.json, totals_by_agent.json | Totals | book expected vs statement paid per carrier or agent NPN, the difference, unexplained revenue, within tolerance; a `not_run_reason` when it did not run |
| rts_coverage.json | RtsCoverage | one cell per agent, carrier, state, and plan year |
| mapping_review.json | MappingReview | written on every run (`items: []` when nothing needs review): `run_id`, `mapping_version` (each source's lineage mapping_version, sorted and joined by commas, or `unmapped` when no mapping ran), `jev_mode`, and one item per header the synonym table and saved decisions did not settle, sorted by source, file, and header. `source` is the mapping key, so the roster's sheets are `roster_agents` and `roster_rts`. Each item: `item_id` ("mr-" plus 12 hex of sha256 of source, file name and header joined by zero bytes), `file_name` (with the sheet in brackets for a workbook sheet, so two files under one source stay apart), header (masked if it looks like an SSN), `format_fingerprint` (16 hex of sha256 of the file's trimmed, lowercased headers joined by newlines, in file order), up to 5 masked samples or none with `samples_withheld`, `allowed_fields`, `proposed_field`, `origin` (`jev_replay` for a saved recording in any mode, `jev_live` or `jev_record` for an API reply in this run, `none` with no answer), `confidence` (the model's own number), `route`, `reason` (for example `mode_off`, `not_recorded`, `invalid_reply`, `http_error`, `notes`, `field_taken`), `rows_with_value`, the linked MAP-001 and MAP-002 `exception_ids`, and a plain `explanation` built from those fields. A reviewer's note at most; it maps, approves, and clears nothing |

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

`agency_schema.run_dir.check_run_dir(path)` validates every file and checks that they agree: manifest and scorecard share run_id and status; scorecard counts match `exceptions.jsonl`; scorecard leg summaries match the leg files; `variances.json` and the leg files list the same leg variances; every variance and RTS gap points at an exception with the right rule; each totals file is grouped the way its name says; a FAILED run has no `clean/`. The sample tests use it now, and the end-to-end tests run it on real output.

## Sample runs (the contract)

`fixtures/sample-run/` (PASSED_WITH_WARNINGS, with examples 3 and 4), `fixtures/sample-run-failed/` (CMP-001, 2,680 expected and 2,574 received, all legs NOT_RUN, empty RTS coverage, no `clean/`), `fixtures/sample-run-passed/` (PASSED, info only), and `fixtures/sample-run-partial/` (a copy of sample-run where the CRM vs statement leg did not run, so two legs ran and one is NOT_RUN with a reason and no counts). Synthetic data. Tests run `check_run_dir` on each one and check that every file is byte-for-byte what the models write, so money can never sneak in as a number. Messages do not repeat raw values; the masked value is in `value_minimized` and amounts are in the tie-out files. When an output model changes, update the samples and regenerate the types.

## Comparing two runs

`uv run intake diff <run_a> <run_b>` prints what changed, in plain language: the status, exception counts by severity, new and resolved exceptions by rule, and each tie-out leg's differences with the dollar change. Exception ids are numbered per run, so two records count as the same problem when they share rule, source, field, and the row's raw hash (or the message, for file-level records). It exits 0, or 1 when a folder is not a run.

## TypeScript for the dashboard

`cd engine && uv run intake schema --ts` writes `dashboard/lib/types.ts` from the JSON Schema in serialization mode (the shape of the files as written). `uv run intake schema --json` prints that schema. A test fails when the committed `types.ts` is out of date.
