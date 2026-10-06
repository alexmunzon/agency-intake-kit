import type { Lineage } from "@/lib/types";

export interface UnresolvedEvidence {
  schema_version: 1;
  run_id: string;
  source: string;
  reason: "crm_absent" | "dob_column_missing" | "dob_blank" | "dob_malformed";
  lineage: Lineage | null;
}
const REASONS = ["crm_absent", "dob_column_missing", "dob_blank", "dob_malformed"];
function fail(where: string): never { throw new Error(`${where}: invalid unresolved evidence`); }
function exact(value: unknown, keys: string[], where: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(where);
  const row = value as Record<string, unknown>;
  if (Object.keys(row).length !== keys.length || keys.some(k => !Object.hasOwn(row, k))) fail(where);
  return row;
}
function nonempty(value: unknown): value is string { return typeof value === "string" && value.length > 0; }
// Count structural colons so JSON.parse cannot silently discard duplicate keys.
function keyCount(text: string): number {
  let quoted = false; let escaped = false; let count = 0;
  for (const char of text) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === ":") count += 1;
  }
  return count;
}
/** Optional browser attachment; references only, never new customer or payment records. */
export function parseUnresolvedEvidence(text: string, runId: string): UnresolvedEvidence[] {
  if (!nonempty(runId)) fail("unresolved_evidence.jsonl");
  if (text === "") return [];
  const lines = text.split("\n");
  if (lines.at(-1) === "") lines.pop();
  const seen = new Set<string>();
  return lines.map((line, index) => {
    const where = `unresolved_evidence.jsonl line ${index + 1}`;
    // JSON numbers for this schema are integers; preserve StrictInt token semantics.
    const tokens = line.matchAll(/"(?:\\.|[^"\\])*"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g);
    if ([...tokens].some(match => match[1] && /[.eE]/.test(match[1]))) fail(where);
    let value: unknown;
    try { value = JSON.parse(line); } catch { fail(where); }
    const row = exact(value, ["schema_version", "run_id", "source", "reason", "lineage"], where);
    if (row.schema_version !== 1 || row.run_id !== runId || !nonempty(row.source)
      || typeof row.reason !== "string" || !REASONS.includes(row.reason)) fail(where);
    if (row.reason === "crm_absent" ? (row.lineage === null) !== (row.source === "crm")
      : row.source !== "crm" || (row.reason !== "dob_column_missing" && row.lineage === null)) fail(where);
    let lineage: Lineage | null = null;
    if (row.lineage !== null) {
      const lin = exact(row.lineage, ["source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version"], where);
      if (![lin.source_file, lin.mapping_version].every(nonempty) || lin.run_id !== runId
        || (lin.sheet !== null && !nonempty(lin.sheet)) || !Number.isSafeInteger(lin.row_number)
        || (lin.row_number as number) < 1 || typeof lin.raw_hash !== "string" || !/^[0-9a-f]{64}$/.test(lin.raw_hash)) fail(where);
      lineage = lin as unknown as Lineage;
    }
    if (keyCount(line) !== (lineage ? 11 : 5)) fail(where);
    const key = JSON.stringify([row.source, row.reason, lineage?.source_file ?? null, lineage?.sheet ?? null, lineage?.row_number ?? null]);
    if (seen.has(key)) fail(where);
    seen.add(key);
    return { schema_version: 1, run_id: runId, source: row.source, reason: row.reason as UnresolvedEvidence["reason"], lineage };
  });
}
