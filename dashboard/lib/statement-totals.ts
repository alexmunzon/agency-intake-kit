import type { Lineage } from "@/lib/types";

export type StatementLineReason = "valid" | "amount_blank" | "amount_malformed" | "amount_mapping_unavailable";
export interface StatementLine { source: string; lineage: Lineage; amount: string | null; reason: StatementLineReason }
export interface StatementTotals {
  schema_version: 1; run_id: string; status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "BLOCKED";
  reason: "excluded_rows" | "no_statements" | "no_statement_rows" | "raw_gate_blocked" | null;
  valid_line_count: number; excluded_line_count: number; total_paid: string | null; lines: StatementLine[];
}

const FILE = "statement_totals.json";
const AMOUNT = /^-?(?:0|[1-9][0-9]{0,9})\.[0-9]{2}$/;
const TOTAL = /^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/;
const REASONS = ["valid", "amount_blank", "amount_malformed", "amount_mapping_unavailable"];
function fail(): never { throw new Error(`${FILE}: invalid or unsupported statement totals`); }
function exact(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const row = value as Record<string, unknown>;
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.hasOwn(row, key))) fail();
  return row;
}
function nonempty(value: unknown): value is string { return typeof value === "string" && value.length > 0; }
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
function money(value: unknown): value is string { return typeof value === "string" && AMOUNT.test(value) && value !== "-0.00"; }
function total(value: unknown): value is string { return typeof value === "string" && TOTAL.test(value) && value !== "-0.00"; }
function sum(lines: StatementLine[]): string {
  const cents = lines.reduce((amount, item) => amount + BigInt(item.amount!.replace(".", "")), BigInt(0));
  const digits = (cents < BigInt(0) ? -cents : cents).toString().padStart(3, "0");
  return `${cents < BigInt(0) ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}
function line(value: unknown, runId: string): StatementLine {
  const row = exact(value, ["source", "lineage", "amount", "reason"]);
  if (!nonempty(row.source) || !row.source.startsWith("statement_")) fail();
  if (typeof row.reason !== "string" || !REASONS.includes(row.reason)) fail();
  if (row.reason === "valid" ? !money(row.amount) : row.amount !== null) fail();
  const lin = exact(row.lineage, ["source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version"]);
  if (!nonempty(lin.source_file) || !nonempty(lin.mapping_version) || lin.run_id !== runId
    || (lin.sheet !== null && !nonempty(lin.sheet)) || !Number.isSafeInteger(lin.row_number)
    || (lin.row_number as number) < 1 || typeof lin.raw_hash !== "string" || !/^[0-9a-f]{64}$/.test(lin.raw_hash)) fail();
  return { source: row.source, lineage: lin as unknown as Lineage, amount: row.amount as string | null,
    reason: row.reason as StatementLineReason };
}

/** Strict optional attachment; errors name the artifact but never repeat input content. */
export function parseStatementTotals(text: string, runId: string): StatementTotals {
  if (!nonempty(runId)) fail();
  // All JSON numbers in this contract are strict integers; amounts are quoted decimal text.
  const tokens = text.matchAll(/"(?:\\.|[^"\\])*"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g);
  if ([...tokens].some(match => match[1] && /[.eE]/.test(match[1]))) fail();
  let value: unknown;
  try { value = JSON.parse(text); } catch { fail(); }
  const row = exact(value, ["schema_version", "run_id", "status", "reason", "valid_line_count", "excluded_line_count", "total_paid", "lines"]);
  if (row.schema_version !== 1 || row.run_id !== runId || !Array.isArray(row.lines)) fail();
  const lines = row.lines.map(value => line(value, runId));
  if (countKeys(text) !== 8 + 10 * lines.length) fail();
  const locations = lines.map(item => JSON.stringify([item.lineage.source_file, item.lineage.sheet, item.lineage.row_number]));
  if (new Set(locations).size !== locations.length) fail();
  const valid = lines.filter(item => item.reason === "valid");
  if (row.valid_line_count !== valid.length || row.excluded_line_count !== lines.length - valid.length) fail();
  if (valid.length === 0 ? row.total_paid !== null : !total(row.total_paid) || row.total_paid !== sum(valid)) fail();
  if (row.status === "AVAILABLE") {
    if (row.reason !== null || lines.length === 0 || valid.length !== lines.length) fail();
  } else if (row.status === "PARTIAL") {
    if (row.reason !== "excluded_rows" || lines.length === 0 || valid.length === lines.length) fail();
  } else if (row.status === "UNAVAILABLE") {
    if (!["no_statements", "no_statement_rows"].includes(row.reason as string) || lines.length !== 0) fail();
  } else if (row.status === "BLOCKED") {
    if (row.reason !== "raw_gate_blocked" || lines.length !== 0) fail();
  } else fail();
  return { schema_version: 1, run_id: runId, status: row.status, reason: row.reason,
    valid_line_count: valid.length, excluded_line_count: lines.length - valid.length,
    total_paid: row.total_paid, lines } as StatementTotals;
}
