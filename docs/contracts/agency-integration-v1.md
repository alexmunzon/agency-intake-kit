# Agency integration contract 1.0.0

Status: implementation contract, 2026-10-07. Synthetic client data only.

## Ownership and entry points

This session owns new adapter modules, the contract, and fixtures. Session 7 owns CLI registration and shared navigation. Existing CLI commands and dashboards are unchanged. The Python entry points will be `intake.adapters.export.export_run`, `bob_resolve.adapters.intake.resolve_intake`, and `plan_diff.adapters.worklist.build_worklist`. Each returns a validated model; callers can serialize with `canonical_json` and must write a new immutable output.

## Version, identity, and hashes

Every packet uses `schema_version: "1.0.0"`, explicit `agency_id`, producer `run_id`, `intake_run_id`, and `data_kind: "synthetic"`. IDs are opaque nonempty strings. Never use an agency name or a filename as an inferred agency ID. Record IDs hash the agency, Intake run, table, artifact hash, and row index. Client and policy IDs remain local to that agency and Intake run. Row hashes and whole-file SHA-256 hashes are different and both are retained.

`artifacts` pins each consumed relative path, exact byte SHA-256, and size. Consumers verify these pins before matching. Missing or stale bytes refuse the operation, never reuse previous results. Pins establish snapshot consistency, not authenticity; a caller must retain a trusted packet. Paths cannot escape the input directory. `provenance` retains source_file, sheet, original row_number, raw_hash, Intake run_id, and mapping_version, plus the exact clean artifact and its data row. Intake row numbers retain their original meaning; no header offset is guessed.

## Clean records and unresolved evidence

`clients` contains only actual clean/clients.csv records. Notes are excluded. `policies` contains only actual clean/policies.csv records with original IDs, line of business, status, plan ID, effective/termination dates, and provenance. Effective date is not an enrollment plan year. Policies are not manufactured into enrollment identities. Missing tables, failed runs, duplicate IDs, missing references, and invalid rows stay visible in `issues`; ambiguous IDs never pick a winner. Intake exceptions and unresolved evidence remain pinned and summarized with row references rather than copied free text.

## Identity and review

`identities` links source record IDs and client IDs to Bob person IDs. State is `resolved`, `unresolved`, `ambiguous`, or `unsupported`. Resolved means Bob's deterministic rules accepted a multi-record identity without pending conflict; it does not mean a human confirmed it. A singleton is unresolved. Gray pairs, cluster conflicts, identity conflicts, and unidentifiable records stay visible. The native Bob result carries scored pairs, golden field provenance, pending pairs, and merge log. No answer key is generated and no benchmark is computed.

Review state is `not_reviewed`, `needs_review`, `approved`, `rejected`, or `blocked`. These adapters only emit the first, second, and last states. Approval/rejection must come from a separate evidenced human decision, never an automatic match or a plan flag.

## Explicit coverage and plan changes

`coverage` is a separate caller-supplied synthetic enrollment evidence file: one row per agency/client/policy/plan/year/county enrollment claim, with provenance. Missing plan_year and county remain null. County is an exact source label within the caller's declared geographic scope (or an explicitly supplied FIPS code); no ZIP-to-county or name-to-FIPS conversion is inferred. Plan matching is exact plan_id + old_year + county membership. V1 supports Medicare Advantage IDs only; other lines of business stay unsupported. Duplicate claims and multiple candidate diffs require review.

The client worklist includes every clean client and all coverage claims, including missing coverage, orphan claims, missing policies, unresolved identities, unsupported plans, incomplete benefits, missing citations, and missing county coverage. Plan Diff artifacts are separately hash-pinned. A matched entry preserves the native PlanDiff with citations and review items. Its shop_again flag is evidence to review, not a suitability or purchase recommendation. No claim of complete client enrollment, real accuracy, or savings is made.

## Compatibility and determinism

Unknown contract versions and unknown model fields fail validation. Additive optional fields require a new minor version and explicit reader support; changed meanings require a major version. Canonical JSON uses sorted keys, UTF-8, no wall-clock fields, stable record ordering, and a trailing newline. Same bytes and options produce identical output. A changed source changes the fingerprint and invalidates earlier pins. Contract models and JSON schema are copied byte-identically across the three repositories until a separately versioned shared package is authorized.

## Reconciled bases

Fetched origin/main on 2026-10-07: Intake 275be53afdc6aecd33ac65defd9c980835127b49; Bob 3ccdbe9420a9f2bb32605574cd027db6f9a8321c; Plan Diff 5b14efc36dace572ff04038c98055209ca768d2a. No newer commits. Existing checkout SPEC.md edits are preserved. Worktrees: aik-contract-adapters, bob-contract-adapters, pd-contract-adapters; branch pr-shared-contract-adapters in each repository. No merge or deployment authorized.
