"""Every threshold, tolerance, and required-field list for the intake pipeline.

Rules for this file:
- One section per PR, in PR order. Add constants only inside your own PR's section.
- Never reorder, rename, or delete an existing constant in another PR's section.
- Type every constant with Final, for example `DOB_MAX_AGE: Final[int] = 115`.
- Business limits live here, never inline in pipeline code.
"""

# PR 4: readers and raw gates (sniffing, header detection, SSN-001, CMP-001, CMP-002)

# PR 5: synonym mapping (required canonical fields per table, MAP-003)

# PR 6: Jev client (retry and backoff, the $0.50 per-run budget)

# PR 7: Jev mapping and enum normalization (confidence cutoffs, MAP-002)

# PR 8: row validators (DOB age range, Medicare age, date rules)

# PR 9: cross-record checks (duplicates, references, RTS, licenses)

# PR 10: three-way tie-out (tolerances: $1 or 1 percent per line, 0.5 percent on totals)

# PR 11: exceptions policy and triage (PII gate cutoff)

# PR 12: run orchestration
