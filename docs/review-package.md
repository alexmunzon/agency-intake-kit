# Unified review summary (unreleased)

`/package` accepts one read-only, explicitly synthetic `review-package-1` JSON snapshot. It does not automatically combine the separately bundled Intake, Bob, readiness, ledger or Plan demos. Refresh clears the view. Same-agency and same-Intake-run imports must retain all existing artifact pins unchanged; explicitly Clear before replacing a snapshot. Failed replacement preserves the prior valid snapshot; Clear invalidates an in-flight import.

The packaging helper requires Node 24 and Python 3 with descriptor-relative file support (macOS and Linux). It reads regular files through pinned directory descriptors, refuses symlinks and special files, and bounds total artifact bytes to 12 MB. Unsupported safe-read platforms fail closed.

Create a basic snapshot from a completed synthetic Intake directory:

```sh
node scripts/review-package.mjs dashboard/public/demo-run synthetic-agency-a --synthetic > /tmp/review-package.json
```

Import that JSON at `/package`. The page checks every included UTF-8 file's byte length and SHA-256, Intake run agreement, counts and native exception/coverage consistency. The agency ID is the explicit producer declaration; hashes establish consistency, not authenticity. The summary shows accepted output rows and distinct source rows with error evidence separately. Raw inputs and mapped output counts have different granularity and are never subtracted to invent an exclusion count.

Optional files must be placed within the same snapshot root and named explicitly after `--synthetic`:

- `source_readiness.json`: existing readiness contract, matching agency and Intake run. Every active version hash must occur in the Intake manifest inputs. Superseded versions remain preserved as history. The existing readiness evaluator supplies dated freshness, expected coverage, owner and next action. Unlinked expected inventories remain unavailable.
- `finance_review.json`: existing neutral finance review. Agency and every row's Intake lineage must agree. The source content hash must match an Intake manifest input. Signed means positive/negative monetary amounts, not digital signature. This is one statement snapshot, not ledger posting.
- `identity_packet.json`: existing agency-integration-v1 Packet schema plus its pinned artifact files (include every referenced path explicitly). The package verifies schema, run/agency, exact artifact pins, native CSV row contents, canonical record IDs, row provenance and the identity partition of the supplied clients. Counts cover supplied records, not a proven complete agency population. Missing identity evidence remains unavailable. Declared approvals are not authenticated.

Example with a real bound identity packet:

```sh
node scripts/review-package.mjs PATH_TO_SNAPSHOT synthetic-agency-a --synthetic identity_packet.json clean/clients.csv clean/policies.csv unresolved_evidence.jsonl > /tmp/review-package.json
```

Only add the actual paths pinned by that packet. Do not relabel separate examples to make scope appear to match. This UI does not import review decisions into another application, authorize release, prove real-client coverage, authenticate a reviewer or post financial entries. Linked guide pages continue to show their own independent data.
