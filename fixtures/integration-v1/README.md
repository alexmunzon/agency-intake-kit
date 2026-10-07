# Synthetic integration fixture v1

The Intake packet and intake-run files are actual pipeline outputs, generated with seed 42,
eight clients, no defect injectors, Jev off, and frozen 2026-10-01 UTC time. Regenerate them
with Intake's `fixtures/integration-v1/generate.py` from its locked engine environment.
No answer key is exported and no benchmark is computed. Notes are absent from the packet.

Bob reads those exact files through the new adapter; all eight people are single-source
records and remain unresolved. bob-result.json (in Bob) preserves native golden field
provenance and matching results. bob-packet.json (in Plan Diff) is its transport packet.

The Plan Diff fixture is an explicitly authored hypothetical enrollment scenario, separate
from Intake: only C-00002 / P-00003 is claimed enrolled for 2026 in Example County, GA.
This scenario does not fill other clients' missing enrollment, and does not assert that the
Intake policy established that enrollment. Its native Plan Diff is generated from synthetic
demo benefit values re-keyed to H8433-008; citations refer to synthetic examples, not actual
carrier documents. The fixture manifest intentionally lists no downloaded source inputs.
Regenerate it with Plan Diff's fixtures/integration-v1/generate.py. Missing enrollment and
unresolved identity remain visible in worklist.json; nothing is a suitability recommendation.
