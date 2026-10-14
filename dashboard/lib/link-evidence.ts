import type { Lineage } from "@/lib/types";

export type LinkState = "confirmed" | "provisional" | "ambiguous" | "unmatched";
export type LinkReason = "strong_key" | "name_dob_only" | "multiple_candidates"
  | "unmatched_strong_key" | "conflicting_name_dob" | "no_candidate";
export type LinkMethod = "MEMBER_ID" | "POLICY_REF" | "NAME_DOB";

export interface LinkCandidate {
  policy_id: string;
  methods: LinkMethod[];
  lineage: Lineage;
}

export interface LinkEvidence {
  schema_version: 1;
  lineage: Lineage;
  state: LinkState;
  reason: LinkReason;
  policy_id: string | null;
  amount: string | null;
  candidates: LinkCandidate[];
}

const FILE = "tie_out/links.jsonl";
const METHODS = ["MEMBER_ID", "POLICY_REF", "NAME_DOB"] as const;
const REASONS: Record<LinkState, LinkReason[]> = {
  confirmed: ["strong_key"],
  provisional: ["name_dob_only"],
  ambiguous: ["multiple_candidates", "unmatched_strong_key", "conflicting_name_dob"],
  unmatched: ["no_candidate"],
};
const LINEAGE_KEYS = ["source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version"];

function fail(where: string): never { throw new Error(`${where}: invalid link evidence`); }
function object(value: unknown, where: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(where);
  return value as Record<string, unknown>;
}
function exact(value: Record<string, unknown>, keys: string[], where: string): void {
  if (Object.keys(value).length !== keys.length || keys.some((key) => !Object.hasOwn(value, key))) fail(where);
}
function nonempty(value: unknown, where: string): asserts value is string {
  if (typeof value !== "string" || value.length === 0) fail(where);
}

// JSON.parse discards duplicate keys. Valid JSON has one structural colon per retained key.
function sourceKeyCount(source: string): number {
  let quoted = false; let escaped = false; let count = 0;
  for (const char of source) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === ":") count += 1;
  }
  return count;
}
function retainedKeyCount(value: unknown): number {
  if (Array.isArray(value)) return value.reduce((sum: number, item) => sum + retainedKeyCount(item), 0);
  if (value !== null && typeof value === "object") {
    return Object.values(value).reduce((sum: number, item) => sum + 1 + retainedKeyCount(item), 0);
  }
  return 0;
}
function parseLine(line: string, where: string): unknown {
  let value: unknown;
  try { value = JSON.parse(line); } catch { fail(where); }
  if (sourceKeyCount(line) !== retainedKeyCount(value)) fail(where);
  return value;
}

function lineage(value: unknown, runId: string, where: string): Lineage {
  const row = object(value, where);
  exact(row, LINEAGE_KEYS, where);
  for (const key of ["source_file", "run_id", "mapping_version"]) nonempty(row[key], where);
  if (row.sheet !== null) nonempty(row.sheet, where);
  if (!Number.isSafeInteger(row.row_number) || (row.row_number as number) < 1) fail(where);
  if (typeof row.raw_hash !== "string" || !/^[0-9a-f]{64}$/.test(row.raw_hash)) fail(where);
  if (row.run_id !== runId) fail(where);
  return row as unknown as Lineage;
}

function candidate(value: unknown, runId: string, where: string): LinkCandidate {
  const row = object(value, where);
  exact(row, ["policy_id", "methods", "lineage"], where);
  nonempty(row.policy_id, where);
  if (!Array.isArray(row.methods) || row.methods.length === 0) fail(where);
  let previous = -1;
  for (const method of row.methods) {
    const index = METHODS.findIndex((known) => known === method);
    if (index <= previous) fail(where);
    previous = index;
  }
  return { policy_id: row.policy_id, methods: row.methods as LinkMethod[],
    lineage: lineage(row.lineage, runId, where) };
}

function evidence(value: unknown, runId: string, where: string): LinkEvidence {
  const row = object(value, where);
  exact(row, ["schema_version", "lineage", "state", "reason", "policy_id", "amount", "candidates"], where);
  if (row.schema_version !== 1 || typeof row.state !== "string" || !Object.hasOwn(REASONS, row.state)) fail(where);
  const state = row.state as LinkState;
  if (!REASONS[state].includes(row.reason as LinkReason)) fail(where);
  if (row.policy_id !== null) nonempty(row.policy_id, where);
  if (row.amount !== null && (typeof row.amount !== "string"
    || !/^-?(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/.test(row.amount))) fail(where);
  if (!Array.isArray(row.candidates)) fail(where);
  const candidates = row.candidates.map((item) => candidate(item, runId, where));
  const ids = candidates.map((item) => item.policy_id);
  if (new Set(ids).size !== ids.length) fail(where);
  if (state === "confirmed") {
    const strong = candidates.filter((item) => item.methods.some((method) => method !== "NAME_DOB"));
    const weak = candidates.filter((item) => item.methods.includes("NAME_DOB"));
    // Name/DOB on other policies may sit beside a confirmed link only when it matched by both
    // strong keys (the engine also requires that policy's client row be missing).
    const bothKeys = strong.length === 1 && strong[0].methods.includes("MEMBER_ID")
      && strong[0].methods.includes("POLICY_REF");
    if (strong.length !== 1 || row.policy_id !== strong[0].policy_id
      || (weak.length > 0 && !weak.some((item) => item.policy_id === row.policy_id) && !bothKeys)) fail(where);
  } else if (row.policy_id !== null) fail(where);
  else if (state === "provisional" && (candidates.length !== 1
    || candidates[0].methods.length !== 1 || candidates[0].methods[0] !== "NAME_DOB")) fail(where);
  else if (state === "ambiguous" && candidates.length === 0) fail(where);
  else if (state === "unmatched" && candidates.length !== 0) fail(where);
  return { schema_version: 1, lineage: lineage(row.lineage, runId, where), state,
    reason: row.reason as LinkReason, policy_id: row.policy_id as string | null,
    amount: row.amount as string | null, candidates };
}

/** Parse an optional line-level review artifact against a run's manifest identity. */
export function parseLinkEvidence(text: string, runId: string): LinkEvidence[] {
  if (!runId) fail(FILE);
  if (text === "") return [];
  const output: LinkEvidence[] = [];
  const seen = new Set<string>();
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    if (index === lines.length - 1 && lines[index] === "") break;
    const where = `${FILE} line ${index + 1}`;
    const item = evidence(parseLine(lines[index], where), runId, where);
    const key = JSON.stringify([item.lineage.source_file, item.lineage.sheet, item.lineage.row_number]);
    if (seen.has(key)) fail(where);
    seen.add(key);
    output.push(item);
  }
  return output;
}
