# Clean row validation

MAP-004 is an Error, not a blocker. Before run status, triage and export, prospective clean
rows must satisfy the existing TABLE_MODELS contracts after the existing typing and status
normalization. Required missing values, invalid enums and typed values that cannot satisfy
those models produce visible exceptions. No model field or blocker policy is weakened.

Each exception identifies table.field and preserves source file, sheet, row, raw hash and
run/mapping version. Display values are minimized from the original canonical cell before
casting. Invalid rows are excluded only from their table, even when a CRM row also supplies
a valid client or policy. An invalid required client or agent also excludes its dependent
policies, primary household or RTS rows with explicit dependency evidence. Existing household
member pruning remains in effect. Optional blanks allowed by the declared schema remain valid.

The pipeline collects these exceptions before status and scorecard calculation. Direct clean
callers receive new records in their supplied exception list. The run writer refuses late
uncollected errors instead of producing an inconsistent status or silent exclusions.
