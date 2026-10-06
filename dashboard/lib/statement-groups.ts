import type { StatementTotals } from "@/lib/statement-totals";

export interface StatementGroup {
  carrier: string | null; statement_period: string | null;
  valid_line_count: number; excluded_line_count: number; total_paid: string | null;
}
const LINEAGE = ["source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version"];
function fail(): never { throw new Error("statement_groups.json: invalid or inconsistent statement grouping"); }
function exact(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const row = value as Record<string, unknown>;
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.hasOwn(row, key))) fail();
  return row;
}
function identity(row: Record<string, unknown>): string { return JSON.stringify(LINEAGE.map(key => row[key])); }
function countKeys(text: string): number {
  let quoted = false; let escaped = false; let count = 0;
  for (const char of text) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === ":") count++;
  }
  return count;
}
/** Join every dimension row to validated amount evidence; never trust a separately supplied sum. */
export function parseStatementGroups(text: string, totals?: StatementTotals): StatementGroup[] {
  if (!totals) fail();
  const tokens = text.matchAll(/"(?:\\.|[^"\\])*"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g);
  if ([...tokens].some(match => match[1] && /[.eE]/.test(match[1]))) fail();
  let value: unknown;
  try { value = JSON.parse(text); } catch { fail(); }
  const top = exact(value, ["schema_version", "run_id", "lines"]);
  if (top.schema_version !== 1 || top.run_id !== totals.run_id || !Array.isArray(top.lines)
    || top.lines.length !== totals.lines.length || countKeys(text) !== 3 + 9 * top.lines.length) fail();
  const available = new Map(totals.lines.map(line => [identity(line.lineage as unknown as Record<string, unknown>), line]));
  const groups = new Map<string, { group: StatementGroup; cents: bigint }>();
  for (const value of top.lines) {
    const row = exact(value, ["lineage", "carrier", "statement_period"]);
    const key = identity(exact(row.lineage, LINEAGE));
    const evidence = available.get(key);
    if (!evidence) fail();
    available.delete(key);
    const carrier = row.carrier; const period = row.statement_period;
    if (carrier !== null && (typeof carrier !== "string" || !carrier || carrier.trim() !== carrier)) fail();
    if (period !== null && (typeof period !== "string" || !/^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$/.test(period))) fail();
    const dimension = JSON.stringify([carrier, period]);
    const entry = groups.get(dimension) ?? { group: { carrier, statement_period: period,
      valid_line_count: 0, excluded_line_count: 0, total_paid: null }, cents: BigInt(0) };
    if (evidence.amount === null) entry.group.excluded_line_count++;
    else { entry.group.valid_line_count++; entry.cents += BigInt(evidence.amount.replace(".", "")); }
    groups.set(dimension, entry);
  }
  if (available.size) fail();
  return [...groups.entries()].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, entry]) => entry).map(({ group, cents }) => {
    const digits = (cents < BigInt(0) ? -cents : cents).toString().padStart(3, "0");
    return { ...group, total_paid: group.valid_line_count === 0 ? null
      : `${cents < BigInt(0) ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)}` };
  });
}
