// Standalone display boundary. No run import, posting or approval authority.
export const CATEGORIES = ["new_business", "renewal", "override", "bonus", "marketing", "unclassified"] as const;
export type RevenueCategory = (typeof CATEGORIES)[number];
export type TransactionKind = "payment" | "reversal" | "adjustment";
export type DecimalString = string;
export interface FinanceLineage {
  source_file: string; sheet: string | null; row_number: number;
  raw_hash: string; run_id: string; mapping_version: string;
}
export interface RevenueMappingSnapshot {
  mapping_id: string; carrier: string; version: string;
  approved_by: string | null; approved_at: string | null;
  categories: Record<string, RevenueCategory>;
  transaction_kinds: Record<string, TransactionKind>;
  accounts: Partial<Record<RevenueCategory, string>>;
}
export interface FinanceReviewRow {
  row_id: string; amount: DecimalString; raw_amount: string;
  raw_category_label: string | null; raw_transaction_label: string | null;
  lineage: FinanceLineage; category: RevenueCategory;
  transaction_kind: TransactionKind | null;
  classification_method: "approved_mapping" | "unresolved";
  unresolved_reasons: string[]; account_code: string | null;
  authoritative_policy_id: null;
}
export interface FinanceReview {
  artifact_type: "neutral_finance_review"; schema_version: 1;
  agency_id: string; carrier: string; period: string;
  statement_id: string; revision_id: string; content_sha256: string;
  mapping_id: string; mapping_version: string; mapping_approved: boolean;
  approved_by: string | null; approved_at: string | null;
  mapping_snapshot: RevenueMappingSnapshot; mapping_sha256: string;
  rows: FinanceReviewRow[]; category_totals: Record<RevenueCategory, DecimalString>;
  statement_total: DecimalString; control_total: DecimalString | null;
  total_check: "PASS" | "FAIL" | "NOT_RUN";
}
type ObjectValue = Record<string, unknown>;
function refuse(): never { throw new Error("Invalid or unsupported finance review artifact"); }
function object(value: unknown): ObjectValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) refuse();
  return value as ObjectValue;
}
function ownValue(value: unknown, key: string): unknown {
  const dictionary = object(value);
  return Object.hasOwn(dictionary, key) ? dictionary[key] : undefined;
}
function keys(value: ObjectValue, expected: string[]) {
  if (Object.keys(value).length !== expected.length || expected.some(k => !Object.hasOwn(value, k))) refuse();
}
function text(value: unknown): asserts value is string {
  if (typeof value !== "string" || !value.trim()) refuse();
}
function nullableText(value: unknown) { if (value !== null) text(value); }
function hash(value: unknown) { if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) refuse(); }
function timestamp(value: unknown) {
  if (value !== null && (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value)))) refuse();
}
function category(value: unknown): asserts value is RevenueCategory {
  if (!CATEGORIES.some(c => c === value)) refuse();
}
function kind(value: unknown) { if (!["payment", "reversal", "adjustment"].includes(value as string)) refuse(); }
// Python Decimal emits fixed or exponent strings; convert directly to integer cents.
function cents(value: unknown): bigint {
  if (typeof value !== "string") refuse();
  const match = /^([+-]?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(value);
  if (!match || value.length > 100) refuse();
  const exponent = Number(match[4] ?? 0);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 100) refuse();
  const digits = match[2] + (match[3] ?? "");
  const shift = 2 + exponent - (match[3]?.length ?? 0);
  let result = BigInt(digits);
  if (shift >= 0) result *= BigInt(10) ** BigInt(shift);
  else {
    const divisor = BigInt(10) ** BigInt(-shift);
    if (result % divisor !== BigInt(0)) refuse();
    result /= divisor;
  }
  return match[1] === "-" ? -result : result;
}
function structuralKeyCount(source: string): number {
  let quoted = false;
  let escaped = false;
  let count = 0;
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
  if (Array.isArray(value)) return value.reduce((sum, item) => sum + retainedKeyCount(item), 0);
  if (value !== null && typeof value === "object") {
    return Object.entries(value).reduce((sum, [, item]) => sum + 1 + retainedKeyCount(item), 0);
  }
  return 0;
}
export function parseFinanceReview(value: unknown): FinanceReview {
  if (typeof value === "string") {
    const source = value;
    try { value = JSON.parse(source); } catch { refuse(); }
    // Valid JSON has one structural colon per retained object key. Duplicate
    // keys discard a key/value, including escaped spellings of the same key.
    if (structuralKeyCount(source) !== retainedKeyCount(value)) refuse();
  }
  // Decoded object inputs remain supported; upstream JSON parsing already
  // loses duplicate-key evidence, so raw text is the preferred file boundary.
  const review = object(value);
  keys(review, ["artifact_type", "schema_version", "agency_id", "carrier", "period", "statement_id", "revision_id", "content_sha256", "mapping_id", "mapping_version", "mapping_approved", "approved_by", "approved_at", "mapping_snapshot", "mapping_sha256", "rows", "category_totals", "statement_total", "control_total", "total_check"]);
  if (review.artifact_type !== "neutral_finance_review" || review.schema_version !== 1 || typeof review.mapping_approved !== "boolean") refuse();
  for (const key of ["agency_id", "carrier", "statement_id", "revision_id", "mapping_id", "mapping_version"]) text(review[key]);
  if (typeof review.period !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(review.period)) refuse();
  hash(review.content_sha256); hash(review.mapping_sha256);
  nullableText(review.approved_by); timestamp(review.approved_at);
  if ((review.approved_by !== null) !== review.mapping_approved || (review.approved_at !== null) !== review.mapping_approved) refuse();
  const mapping = object(review.mapping_snapshot);
  keys(mapping, ["mapping_id", "carrier", "version", "approved_by", "approved_at", "categories", "transaction_kinds", "accounts"]);
  for (const [key, parent] of [["mapping_id", "mapping_id"], ["carrier", "carrier"], ["version", "mapping_version"], ["approved_by", "approved_by"], ["approved_at", "approved_at"]]) if (mapping[key] !== review[parent]) refuse();
  for (const [label, mapped] of Object.entries(object(mapping.categories))) { text(label); category(mapped); }
  for (const [label, mapped] of Object.entries(object(mapping.transaction_kinds))) { text(label); kind(mapped); }
  for (const [mapped, account] of Object.entries(object(mapping.accounts))) { category(mapped); text(account); }
  if (!Array.isArray(review.rows)) refuse();
  const sums = Object.fromEntries(CATEGORIES.map(c => [c, BigInt(0)])) as Record<RevenueCategory, bigint>;
  const ids = new Set<string>();
  const reasons = ["mapping_not_approved", "unknown_category_label", "unknown_transaction_label", "missing_account_mapping"];
  for (const valueRow of review.rows) {
    const row = object(valueRow);
    keys(row, ["row_id", "amount", "raw_amount", "raw_category_label", "raw_transaction_label", "lineage", "category", "transaction_kind", "classification_method", "unresolved_reasons", "account_code", "authoritative_policy_id"]);
    text(row.row_id); if (ids.has(row.row_id)) refuse(); ids.add(row.row_id);
    const amount = cents(row.amount); if (amount !== cents(row.raw_amount)) refuse();
    category(row.category); if (row.transaction_kind !== null) kind(row.transaction_kind);
    nullableText(row.raw_category_label); nullableText(row.raw_transaction_label); nullableText(row.account_code);
    if (row.authoritative_policy_id !== null || !["approved_mapping", "unresolved"].includes(row.classification_method as string)) refuse();
    if (!Array.isArray(row.unresolved_reasons) || row.unresolved_reasons.some(r => !reasons.includes(r))) refuse();
    if (row.classification_method === "approved_mapping" && (!review.mapping_approved || row.category === "unclassified" || row.transaction_kind === null)) refuse();
    if (row.classification_method === "unresolved" && row.unresolved_reasons.length === 0) refuse();
    const mappedCategory = review.mapping_approved ? ownValue(mapping.categories, (row.raw_category_label as string | null) ?? "") : undefined;
    const mappedKind = review.mapping_approved ? ownValue(mapping.transaction_kinds, (row.raw_transaction_label as string | null) ?? "") : undefined;
    const expectedCategory = mappedCategory ?? "unclassified";
    const expectedKind = mappedKind ?? null;
    const expectedAccount = review.mapping_approved ? ownValue(mapping.accounts, expectedCategory as string) ?? null : null;
    const expectedReasons: string[] = [];
    if (!review.mapping_approved) expectedReasons.push("mapping_not_approved");
    else {
      if (!mappedCategory || mappedCategory === "unclassified") expectedReasons.push("unknown_category_label");
      if (!mappedKind) expectedReasons.push("unknown_transaction_label");
    }
    if (expectedAccount === null) expectedReasons.push("missing_account_mapping");
    const expectedMethod = review.mapping_approved && expectedKind !== null && expectedCategory !== "unclassified" ? "approved_mapping" : "unresolved";
    if (row.category !== expectedCategory || row.transaction_kind !== expectedKind || row.account_code !== expectedAccount || row.classification_method !== expectedMethod || JSON.stringify(row.unresolved_reasons) !== JSON.stringify(expectedReasons)) refuse();
    const lineage = object(row.lineage);
    keys(lineage, ["source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version"]);
    for (const k of ["source_file", "run_id", "mapping_version"]) text(lineage[k]);
    nullableText(lineage.sheet); hash(lineage.raw_hash);
    if (!Number.isSafeInteger(lineage.row_number) || (lineage.row_number as number) < 1) refuse();
    sums[row.category] += amount;
  }
  const totals = object(review.category_totals); keys(totals, [...CATEGORIES]);
  let sum = BigInt(0);
  for (const c of CATEGORIES) { if (cents(totals[c]) !== sums[c]) refuse(); sum += sums[c]; }
  if (cents(review.statement_total) !== sum) refuse();
  const check = review.control_total === null ? "NOT_RUN" : cents(review.control_total) === sum ? "PASS" : "FAIL";
  if (review.total_check !== check) refuse();
  // Rebuild from JSON so callers cannot retain aliases to an unvalidated object.
  return JSON.parse(JSON.stringify(review)) as FinanceReview;
}

// Shared exact decimal parser for ledger conservation checks.
export { cents as financeCents };
