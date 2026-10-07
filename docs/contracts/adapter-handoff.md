# Adapter integration handoff

Contract: [agency-integration-v1.md](agency-integration-v1.md). These are pure library entry
points; Session 7 owns CLI/navigation and immutable output writing. They never mutate inputs.

```python
# Intake environment
from intake.adapters.export import export_run
from intake.adapters.contract import canonical_json
packet = export_run(intake_run_dir, agency_id="synthetic-agency-a", data_kind="synthetic")
serialized = canonical_json(packet)

# Bob environment (load transport using Bob's contract model)
from datetime import date
from bob_resolve.adapters.contract import Packet, canonical_json
from bob_resolve.adapters.intake import resolve_intake
result = resolve_intake(Packet.model_validate_json(serialized), intake_run_dir,
                        run_id="bob-1", as_of=date(2026, 10, 1), shared_ids=True)
serialized_bob_packet = canonical_json(result.packet)

# Plan Diff environment
from plan_diff.adapters.contract import Packet, pin, canonical_json
from plan_diff.adapters.worklist import build_worklist, pin_plan_run
# Capture pins once from trusted inputs and retain them; do not re-pin on a stale rerun.
coverage_pin = pin(coverage_dir, "coverage.json")
plan_pins = pin_plan_run(plan_run_dir)
worklist = build_worklist(Packet.model_validate_json(serialized_bob_packet), intake_run_dir,
                         coverage_root=coverage_dir, coverage_artifact=coverage_pin,
                         plan_root=plan_run_dir, plan_artifacts=plan_pins, run_id="worklist-1")
serialized_worklist = canonical_json(worklist)
```

Callers must supply Path instances, explicit agency and run IDs, a frozen Bob as_of date,
and an explicit synthetic-data attestation. Save the entire Bob result as well as its packet
if native scored pairs, conflict detail, golden fields, and merge log are needed. No answer key
is requested. Prior review decisions are not imported or applied by these entry points.

A missing/stale pinned file, path escape, malformed native review artifact, or invalid
contract raises ValueError, ValidationError, or an OSError. Preserve the prior output on any
failure. Missing clean tables/rows and incomplete coverage produce visible issues/items.
These are different outcomes: an invalid snapshot cannot safely produce a worklist.

The packet pins manifest.json, clean clients/policies, exceptions, and unresolved evidence.
Original raw-input whole-file hashes remain in that pinned Intake manifest, while each clean
row retains its original raw-row hash. Raw drop files are not re-opened. Plan pins cover the
manifest, native plan/diff JSON, and review queue; PDF/CMS source bytes are not re-downloaded
or revalidated. Hash pins prove byte consistency against a trusted packet, not authenticity.

County comparisons are exact within the supplied scope; no county aliases, ZIP conversion,
state disambiguation, or cross-agency identity matching is attempted. Missing or unsupported
coverage stays visible. The native shop_again field remains evidence to review, never a
personal suitability finding. All worklist entries require human review.

Frozen source files and their hashes are listed in the external transfer manifest supplied
to Session 7. Full combined repository gates and commits are owned by Session 7; these builder
worktrees run focused tests/static checks and remain preserved. No push, merge, or deployment
is authorized by this handoff.

## Orchestration rule (carry into every future handoff)

Astra orchestrates planning, delegation, review, and integration. Explicitly designated Sol
workers implement, debug, test, and perform routine verification; Astra does not substitute
for those workers. Divide independent work in parallel with one clear owner per repository
or worktree, follow the GYDE recruiting scope and the Session 1 contract, and preserve saved
work. Session 7 alone owns merges and deployments. Deliver tested commits and clear handoffs
through the authorized integration workflow; builder worktrees provide focused check
evidence before Session 7 runs the serialized full gates and creates those commits. Report
states and blockers only from evidence, and preserve this rule in all future handoffs.
