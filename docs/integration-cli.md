# Offline integration CLI

These commands exchange synthetic review evidence between Intake, Bob Resolve, and
Plan Diff. Run them from the workspace containing the three release checkouts.
They use saved local fixtures and make no model calls or downloads.

The examples use explicit IDs from `fixtures/integration-v1`. For another saved
run, supply its actual manifest ID, the intended agency ID, and Bob's explicit
frozen date. Agency IDs are opaque values supplied by the caller.

```sh
mkdir -p /private/tmp/agency-integration-cli

uv run --locked --project release-intake-20261007/engine intake integration export \
  --run release-intake-20261007/fixtures/integration-v1/intake-run \
  --agency-id synthetic-agency-a --run-id intake-synthetic-v1 \
  --data-kind synthetic --out /private/tmp/agency-integration-cli/intake-packet.json

uv run --locked --project release-bob-20261007/engine bob-resolve integration resolve \
  --packet /private/tmp/agency-integration-cli/intake-packet.json \
  --intake-root release-intake-20261007/fixtures/integration-v1/intake-run \
  --agency-id synthetic-agency-a --intake-run-id intake-synthetic-v1 \
  --run-id bob-cli-v1 --as-of 2026-10-01 --data-kind synthetic \
  --out /private/tmp/agency-integration-cli/bob-resolution.json

uv run --locked --project release-bob-20261007/engine bob-resolve integration packet \
  --resolution /private/tmp/agency-integration-cli/bob-resolution.json \
  --agency-id synthetic-agency-a --run-id bob-cli-v1 --data-kind synthetic \
  --out /private/tmp/agency-integration-cli/bob-packet.json

uv run --locked --project release-plan-20261007/engine plan-diff integration pin \
  --coverage-root release-plan-20261007/fixtures/integration-v1 \
  --coverage coverage.json \
  --plan-root release-plan-20261007/fixtures/integration-v1/plan-run \
  --agency-id synthetic-agency-a --plan-run-id plan-synthetic-v1 \
  --data-kind synthetic --out /private/tmp/agency-integration-cli/pins.json

uv run --locked --project release-plan-20261007/engine plan-diff integration worklist \
  --packet /private/tmp/agency-integration-cli/bob-packet.json \
  --pins /private/tmp/agency-integration-cli/pins.json \
  --intake-root release-intake-20261007/fixtures/integration-v1/intake-run \
  --coverage-root release-plan-20261007/fixtures/integration-v1 \
  --plan-root release-plan-20261007/fixtures/integration-v1/plan-run \
  --agency-id synthetic-agency-a --bob-run-id bob-cli-v1 \
  --run-id worklist-cli-v1 --data-kind synthetic \
  --out /private/tmp/agency-integration-cli/worklist.json
```

Use a new output filename or directory for a repeat run. Every command writes a
complete canonical UTF-8 JSON file atomically and refuses an existing file,
including a concurrently published output. There is no overwrite option.
Identical input bytes, IDs, date, and options produce identical output bytes.
Malformed inputs, mismatched IDs, missing evidence, and stale hashes exit with
code 2 without publishing an output. Refusal messages omit rejected source values;
accepted source issues remain in the packet or worklist rather than disappearing.

The Intake export contains actual clean clients and policies, source provenance,
and references to unresolved evidence. Failed runs and missing clean tables remain
visible as issues. It does not create enrollment records from policies.

Bob's resolution file is an envelope containing the native resolution, scored
pairs, dropped candidate blocks, frozen date, shared-ID setting, and integration
packet. The `packet` command extracts that validated packet to a new file for
Plan Diff. Keep the original envelope: the packet does not contain all native
scoring and merge evidence. Resolved identities describe deterministic matches;
they are not human approval. Singletons and pending conflicts remain unresolved
or ambiguous. Use `--no-shared-ids` on `resolve` to disable shared-ID matching.

Plan Diff's `pin` command freezes the explicit coverage JSON, its referenced source
files, and the saved plan artifact inventory. Retain that pins file and pass it
unchanged to `worklist`. If coverage, Intake, or plan bytes change, worklist refuses
stale evidence; if a plan artifact is added or removed, it refuses the changed
inventory. Deliberately create a new pins file only when adopting a new snapshot.
Hashes establish byte consistency, not authentication: retain trusted packets,
pins, and their original evidence.

Coverage must be a contract `CoverageFile` with explicit enrollment claims and
pinned source provenance. Plan year and county are never inferred from policy
start dates or ZIP codes. The worklist retains every clean client and coverage
claim, including missing evidence, orphans, unsupported plans, unresolved
identities, native Plan Diff citations, and review reasons. All worklist items
require review; a plan's shop-again flag is not a suitability or purchase
recommendation. The integration commands accept only explicitly labeled synthetic
evidence. Existing Plan Diff public-data commands keep their separate purpose.
