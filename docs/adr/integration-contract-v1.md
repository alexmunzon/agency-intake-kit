# Integration contract v1

Use a strict versioned JSON packet as the boundary between the three engines. Vendor the
small contract models and generated schemas byte-identically in each repository for now;
do not add a cross-repository runtime dependency or change locked dependency versions.
New versions must update each consumer explicitly. Contract/schema parity is checked in the
transfer manifest and schema tests. A separately published shared package is deferred.

Reuse native Bob matching and native Plan Diff artifacts. Keep Intake client records distinct
from enrollment evidence. Coverage is supplied explicitly, including year and county; absent
values remain review gaps. Native deterministic decisions never count as human approval.

Keep CLI/navigation registration separate (Session 7). The adapter APIs are documented in
../contracts/adapter-handoff.md. No network/model calls, benchmark truth, or suitability output.
