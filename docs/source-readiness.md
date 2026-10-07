# Source readiness

Synthetic file coverage is tracked independently of pipeline success, signed financial totals, identity resolution and human approval. Open `/readiness` directly. Session 7 owns shared navigation and registration of `intake.source_readiness_cli:app` under `intake readiness`; those shared files are deliberately unchanged here.

## Workflow and examples

Run from `engine/` before shared CLI registration:

```sh
uv run python -m intake.source_readiness_cli check ../fixtures/source-readiness/demo.json
uv run python -m intake.source_readiness_cli import ../fixtures/source-readiness/corrected.json --out ../runs/readiness-local.json
uv run python -m intake.source_readiness_cli export ../runs/readiness-local.json --out ../runs/onboarding-example.zip
```

The page imports the same JSON format, validates all embedded evidence hashes and references, and allows owner/next-action edits on expectations. Download the reusable JSON package before leaving. Importing malformed JSON, invalid dates, broken correction links, unsupported versions, duplicate keys or changed evidence bytes preserves the previous valid view. Clearing invalidates outstanding imports. The CLI validates before atomically replacing a local snapshot; failed writes preserve the previous file. For an existing agency/run, imports must retain every prior version, receipt and evidence item unchanged, cannot move the clock backward, and cannot change an established Intake run link. They may append deliveries/corrections and update expectation planning metadata. A corrupt prior disk snapshot is refused even when switching packages; choose a new output path for recovery. The browser enforces the same continuity for its current package, and preserves prior ownership/action edits on rejection. Export refuses existing output, including symlinks.

`fixtures/source-readiness/` includes current, missing, stale, unknown, wrong-period, duplicate, conflicting, corrected and absent-inventory packages. `demo.json` combines all five states. Every byte is synthetic.

## Coverage and history rules

One package has an explicit agency ID and can contain any number of carriers, file types and monthly periods. Cross-agency references are refused. IDs and labels are exact, opaque strings, not inferred aliases. An expected scope is `(agency_id, carrier, file_type, period)`. Repeating an expected scope is malformed. Neither a null nor an empty inventory can be complete. Unexpected versions stay visible and do not cover a different period.

Each expectation states its minimum source date, owner and next action. Unknown dates, cutoffs, owners and actions are explicit nulls. A receipt records its delivery ID, immutable version ID, received timestamp, owner and next action. Version metadata pins the original file name, SHA-256, source date and superseded version. Evidence carries exact UTF-8 bytes as a string and validates their SHA-256.

Only delivered versions count. Multiple receipts for identical evidence are retained without increasing coverage. A delivered correction supersedes its named version and ancestors. Duplicate aliases with equivalent correction ancestry also stay superseded. Parent aliases normalize recursively; a same-byte correction remains a distinct generation. Corrections across scopes, absent targets and cycles are malformed. Independent active versions with different hashes or source dates are conflicting, including competing corrections. No latest-delivery winner is chosen. A candidate correction with no delivery cannot replace a delivered source.

An exact expected scope is missing with no active delivery, conflicting with distinct active evidence, unknown without a source date or cutoff, stale below the cutoff, and current at/after the cutoff. Overall priority is conflicting, missing, unknown, stale, current. Coverage is complete only when a nonempty inventory is entirely current. This does not approve the package. Freshness is evaluated against the package's explicit `as_of` snapshot; the page never implies a live refresh.

## Session 1 contract alignment

This is a named readiness extension of the `1.0.0` contract in Session 1's `docs/contracts/agency-integration-v1.md`, not a clean-client `Packet`. Both JSON and onboarding manifest use `schema_version: "1.0.0"`, explicit `agency_id`, `run_id` and `data_kind: "synthetic"`. `intake_run_id` is explicitly null before Intake runs; it is never manufactured from a filename. If supplied, it records a caller assertion rather than a verified clean-output link.

The onboarding ZIP includes the full reusable `source_readiness.json`, recomputed `readiness_summary.json`, original evidence under content-addressed `evidence/<sha256>.txt`, and `onboarding_manifest.json`. Manifest `artifacts` have exactly Session 1's `path`, `sha256`, `size_bytes` fields, pinning every other member. Canonical JSON uses sorted keys, UTF-8 and a trailing newline. ZIP order and timestamps are fixed. Equal input yields equal bytes. All exported paths are generated locally, never taken from an imported file name. `review_state` is always `not_reviewed`. Raw files have file-level provenance; no sheet, row number, row hash or mapping version is invented for unparsed source bytes. Original names and correction/receipt history remain in the readiness JSON.

The superseded-version pointer resolves to the exact prior version and its pinned file hash within the validated package, preserving the prior bytes. Session 1 approved this named readiness extension through Session 7; artifact kind and version must both match.

Pins prove internal byte consistency, not authenticity. A malicious party could change bytes and recompute hashes. Retain a trusted archive externally. No inventory completeness or operational accuracy can be inferred from these synthetic examples.

## Storage and limitations

The browser uses component memory only, with no localStorage, database or server writes. Downloads are local files retained by the user. CLI imports persist one atomic local disk snapshot across restarts; this is not a concurrent receipt database, hosted durable service, authenticated audit log or backup system. A valid import for a different agency/run intentionally switches packages and replaces the snapshot. The page displays the new agency/run; clear also deliberately resets browser memory. Same-package imports preserve recorded evidence through continuity checks. Use separate disk paths for different packages you want to retain. Concurrent CLI writers are unsupported; this snapshot operation is not a transactional multi-writer ledger. Original receipts/versions inside a snapshot remain intact during evaluation/export, but owner/action edits are local planning metadata, not authenticated events.

V1 supports embedded UTF-8 synthetic files and monthly periods. Binary XLSX/PDF payloads, automatic carrier collection, carrier logins, real client data, incremental event ingestion, multi-user updates, authenticated approval and automatic downstream posting are outside scope. Reuse the JSON or archive without uploading original evidence again; clean-record onboarding adapters must independently validate/map it before any loading. The public demo and existing source/finance pages remain unchanged.

## Reconciliation

Based on fetched main `275be53afdc6aecd33ac65defd9c980835127b49`. The saved `build/m2-sources` worktree is clean at `e9a759399fed447fd0bd3c659055f0b04faa89c9` and has no source-readiness implementation or unique branch diff to recover. Historical handoffs confirm this; saved worktrees, stashes and the primary checkout's unrelated SPEC edit were preserved.
