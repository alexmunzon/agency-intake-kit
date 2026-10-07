// Shapes come from lib/types.ts, generated from engine/src/agency_schema/mapping_review.py (interface
// 2026-10-06). The review file is optional; the decisions file is a reviewer's note that is downloaded,
// never sent anywhere, and carries no authority.

import type {
  JevMode, MappingDecision, MappingDecisions, MappingReview, MappingReviewItem,
} from "@/lib/types";

export type { JevMode, MappingDecision, MappingDecisions, MappingReview, MappingReviewItem };
export type MappingOrigin = MappingReviewItem["origin"];
export type MappingRoute = MappingReviewItem["route"];
export type MappingAction = MappingDecision["action"];

export const DECISIONS_NOTE: MappingDecisions["note"] = "a reviewer's note, not an authenticated approval";

/** What the page shows: nothing (no file), the review, or a plain error. */
export type MappingReviewState = { ok: true; review: MappingReview } | { ok: false; error: string };

/** A choice held in the page. "leave" (the default) is the absence of a decision. */
export type MappingChoice =
  | { action: "leave" }
  | { action: "approve" }
  | { action: "correct"; field: string | null }
  | { action: "ignore" };

export const MAPPING_REVIEW_FILE = "mapping_review.json";
const MODES = ["off", "replay", "live", "record"];
const ORIGINS = ["jev_replay", "jev_live", "jev_record", "none"];
const ROUTES = ["auto", "suggest", "unmapped", "person"];
const ITEM_ID = /^mr-[0-9a-f]{12}$/;
const FINGERPRINT = /^[0-9a-f]{16}$/;
const FIELD_REF = /^([a-z_]+\.[a-z0-9_]+|none)$/;
const MAX_SAMPLES = 5;

function fail(problem: string): never {
  throw new Error(`${MAPPING_REVIEW_FILE}: ${problem}`);
}
function record(value: unknown, where: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(`${where} must be an object`);
  return value as Record<string, unknown>;
}
function text(value: unknown, where: string): string {
  if (typeof value !== "string" || value === "") fail(`${where} must be non-empty text`);
  return value;
}
function texts(value: unknown, where: string): string[] {
  if (!Array.isArray(value)) fail(`${where} must be a list`);
  return value.map((entry) => text(entry, where));
}
function oneOf<T extends string>(value: unknown, options: string[], where: string): T {
  if (typeof value !== "string" || !options.includes(value)) fail(`${where} is not a known value`);
  return value as T;
}
function pattern(value: unknown, re: RegExp, where: string): string {
  if (typeof value !== "string" || !re.test(value)) fail(`${where} is not in the expected format`);
  return value;
}

function parseItem(value: unknown, index: number): MappingReviewItem {
  const where = `item ${index + 1}`;
  const raw = record(value, where);
  const allowed = texts(raw.allowed_fields, `${where} allowed_fields`).map((f) => pattern(f, FIELD_REF, `${where} allowed field`));
  const samples = texts(raw.samples, `${where} samples`);
  if (typeof raw.samples_withheld !== "boolean") fail(`${where} samples_withheld must be true or false`);
  if (samples.length > MAX_SAMPLES) fail(`${where} has more than ${MAX_SAMPLES} samples`);
  if (raw.samples_withheld && samples.length > 0) fail(`${where} withholds samples but lists some`);
  const proposed = raw.proposed_field === null ? null : pattern(raw.proposed_field, FIELD_REF, `${where} proposed_field`);
  if (proposed !== null && !allowed.includes(proposed)) fail(`${where} proposes a field that is not allowed`);
  const origin = oneOf<MappingOrigin>(raw.origin, ORIGINS, `${where} origin`);
  const confidence = raw.confidence;
  if (confidence !== null && (typeof confidence !== "number" || !(confidence >= 0 && confidence <= 1))) fail(`${where} confidence must be between 0 and 1`);
  if (origin === "none" && confidence !== null) fail(`${where} has a confidence but no model answer`);
  const rows = raw.rows_with_value;
  if (typeof rows !== "number" || !Number.isSafeInteger(rows) || rows < 0) fail(`${where} rows_with_value must be a whole number`);
  return {
    item_id: pattern(raw.item_id, ITEM_ID, `${where} item_id`),
    source: text(raw.source, `${where} source`),
    file_name: text(raw.file_name, `${where} file_name`),
    header: text(raw.header, `${where} header`),
    format_fingerprint: pattern(raw.format_fingerprint, FINGERPRINT, `${where} format_fingerprint`),
    samples,
    samples_withheld: raw.samples_withheld,
    allowed_fields: allowed,
    proposed_field: proposed,
    origin,
    confidence,
    route: oneOf<MappingRoute>(raw.route, ROUTES, `${where} route`),
    reason: raw.reason === null ? null : text(raw.reason, `${where} reason`),
    rows_with_value: rows,
    exception_ids: texts(raw.exception_ids, `${where} exception_ids`),
    explanation: text(raw.explanation, `${where} explanation`),
  };
}

/** Checks the shape defensively and rebuilds a clean copy. Throws one plain message naming the file. */
export function parseMappingReview(source: string, runId: string): MappingReview {
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    fail("not valid JSON");
  }
  const raw = record(value, "the file");
  const run = text(raw.run_id, "run_id");
  if (run !== runId) fail("from a different run");
  if (!Array.isArray(raw.items)) fail("items must be a list");
  const items = raw.items.map(parseItem);
  if (new Set(items.map((item) => item.item_id)).size !== items.length) fail("an item appears more than once");
  return {
    run_id: run,
    mapping_version: text(raw.mapping_version, "mapping_version"),
    jev_mode: oneOf<JevMode>(raw.jev_mode, MODES, "jev_mode"),
    items,
  };
}

/** Missing file means no panel; a malformed one becomes an error the panel shows instead of crashing. */
export function readMappingReview(source: string | undefined, runId: string): MappingReviewState | undefined {
  if (source === undefined) return undefined;
  try {
    return { ok: true, review: parseMappingReview(source, runId) };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}

/** Fields a reviewer may correct to. "none" is offered as "Ignore this column" instead. */
export function correctableFields(item: MappingReviewItem): string[] {
  return item.allowed_fields.filter((field) => field !== "none");
}

export function canApprove(item: MappingReviewItem): boolean {
  return item.proposed_field !== null && item.proposed_field !== "none";
}

/** Builds the decisions file exactly per interface section 2. Unfinished corrections stay unresolved. */
export function buildDecisions(
  review: MappingReview, choices: Record<string, MappingChoice>, reviewer: string, decidedAt: string,
): MappingDecisions {
  const name = reviewer.trim();
  if (!name) throw new Error("Type your name before downloading.");
  const decisions: MappingDecision[] = [];
  for (const item of review.items) {
    const choice = choices[item.item_id];
    if (!choice || choice.action === "leave") continue;
    let field: string | null = null;
    if (choice.action === "approve") {
      if (!canApprove(item)) throw new Error(`${item.header}: there is no proposal to approve.`);
      field = item.proposed_field;
    } else if (choice.action === "correct") {
      if (choice.field === null) continue;
      if (!correctableFields(item).includes(choice.field)) throw new Error(`${item.header}: that field is not allowed for this column.`);
      field = choice.field;
    }
    decisions.push({
      item_id: item.item_id, source: item.source, header: item.header,
      format_fingerprint: item.format_fingerprint, action: choice.action, field,
    });
  }
  return {
    run_id: review.run_id, mapping_version: review.mapping_version, reviewer: name,
    decided_at: decidedAt, note: DECISIONS_NOTE, decisions,
  };
}

/**
 * Plain warnings for choices `intake mapping apply` would refuse: two columns of one source set to
 * the same field, or the same column in two files given different decisions. Empty when none.
 */
export function decisionConflicts(review: MappingReview, choices: Record<string, MappingChoice>): string[] {
  const fields = new Map<string, Set<string>>(); // "source field" -> headers set to it
  const perColumn = new Map<string, Set<string>>(); // "source header" -> distinct decisions
  for (const item of review.items) {
    const choice = choices[item.item_id];
    if (!choice || choice.action === "leave") continue;
    if (choice.action === "correct" && choice.field === null) continue;
    const field = choice.action === "approve" ? item.proposed_field : choice.action === "correct" ? choice.field : null;
    const column = `${item.source}\u0000${item.header}`;
    perColumn.set(column, (perColumn.get(column) ?? new Set()).add(`${choice.action}:${field ?? ""}`));
    if (field !== null && field !== "none") {
      const key = `${item.source}\u0000${field}`;
      fields.set(key, (fields.get(key) ?? new Set()).add(item.header));
    }
  }
  const problems: string[] = [];
  for (const [key, headers] of fields) {
    const [source, field] = key.split("\u0000");
    if (headers.size > 1) problems.push(`Two columns in ${source} are set to ${field}. Pick a different field or ignore one of them.`);
  }
  for (const [column, decided] of perColumn) {
    const [source, header] = column.split("\u0000");
    if (decided.size > 1) problems.push(`${header} in ${source} has different decisions in two files. Make them match.`);
  }
  return problems;
}

export function decisionsFileName(runId: string): string {
  return `mapping-decisions-${runId}.json`;
}
