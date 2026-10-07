import { CATEGORIES, financeCents as cents, parseFinanceReview, type FinanceReview, type RevenueCategory } from './finance-review';

export interface LedgerReceipt {
  receipt_id: string; received_at: string; replaces_revision_id: string | null;
  logical_key: [string, string, string, string]; revision_id: string;
  canonical_rows_sha256: string;
  state: 'active' | 'duplicate' | 'superseded' | 'conflict'; reason: string | null;
}
export interface LedgerTotal {
  agency_id: string; carrier: string; period: string;
  category_totals: Record<RevenueCategory, string>; statement_total: string;
}
export interface FinanceLedger {
  artifact_type: 'neutral_finance_ledger'; schema_version: 1;
  receipts: LedgerReceipt[]; revisions: unknown[]; active_reviews: FinanceReview[];
  conflicts: FinanceReview[]; grouped_totals: LedgerTotal[];
  unresolved_conflict_totals: LedgerTotal[];
}
function refuse(): never { throw new Error('Invalid or inconsistent ledger export'); }
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) refuse();
  return v as Record<string, unknown>;
}
function text(v: unknown): v is string { return typeof v === 'string' && v.trim().length > 0; }
export function parseFinanceLedger(source: string): FinanceLedger {
  // Count structural object keys before JSON.parse discards duplicate keys.
  const stripped = source.replace(/"(?:[^"\\]|\\.)*"/g, '""');
  const value: unknown = JSON.parse(source);
  function count(v: unknown): number {
    if (Array.isArray(v)) return v.reduce((n, item) => n + count(item), 0);
    if (v && typeof v === 'object') return Object.values(v).reduce<number>((n, item) => n + 1 + count(item), 0);
    return 0;
  }
  if ((stripped.match(/:/g) ?? []).length !== count(value)) refuse();
  const v = object(value);
  const fields = ['artifact_type', 'schema_version', 'receipts', 'revisions', 'active_reviews', 'conflicts', 'grouped_totals', 'unresolved_conflict_totals'];
  if (Object.keys(v).length !== fields.length || fields.some(k => !Object.hasOwn(v, k)) || v.schema_version !== 1 || v.artifact_type !== 'neutral_finance_ledger') refuse();
  for (const key of fields.slice(2)) if (!Array.isArray(v[key])) refuse();
  const active = (v.active_reviews as unknown[]).map(parseFinanceReview);
  const conflicts = (v.conflicts as unknown[]).map(parseFinanceReview);
  const ids = new Set();
  let previousTime = -Infinity;
  for (const item of v.receipts as unknown[]) {
    const r = object(item);
    const receiptFields = ['receipt_id', 'received_at', 'replaces_revision_id', 'logical_key', 'revision_id', 'canonical_rows_sha256', 'state', 'reason'];
    if (Object.keys(r).length !== receiptFields.length || receiptFields.some(key => !Object.hasOwn(r, key))) refuse();
    if (!text(r.receipt_id) || ids.has(r.receipt_id) || !text(r.revision_id) || !text(r.received_at) || !Number.isFinite(Date.parse(r.received_at)) || !['active', 'duplicate', 'superseded', 'conflict'].includes(r.state as string)) refuse();
    const receivedTime = Date.parse(r.received_at);
    if (receivedTime < previousTime) refuse();
    previousTime = receivedTime;
    ids.add(r.receipt_id);
    if (!Array.isArray(r.logical_key) || r.logical_key.length !== 4 || !r.logical_key.every(text) || typeof r.canonical_rows_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(r.canonical_rows_sha256)) refuse();
    if (r.replaces_revision_id !== null && !text(r.replaces_revision_id)) refuse();
    if (r.reason !== null && !text(r.reason)) refuse();
  }
  if ((v.receipts as unknown[]).length !== (v.revisions as unknown[]).length) refuse();
  (v.revisions as unknown[]).forEach((item, index) => {
    const p = object(item);
    const receipt = (v.receipts as LedgerReceipt[])[index];
    const revisionFields = ['agency_id', 'carrier', 'period', 'statement_id', 'revision_id', 'content_sha256', 'expected_row_count', 'rows', 'control_total'];
    if (Object.keys(p).length !== revisionFields.length || revisionFields.some(key => !Object.hasOwn(p, key))) refuse();
    if (JSON.stringify([p.agency_id, p.carrier, p.period, p.statement_id]) !== JSON.stringify(receipt.logical_key) || p.revision_id !== receipt.revision_id || typeof p.content_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(p.content_sha256)) refuse();
    if (!Array.isArray(p.rows) || !Number.isSafeInteger(p.expected_row_count) || p.expected_row_count !== p.rows.length) refuse();
    const rowIds = new Set();
    for (const raw of p.rows) {
      const row = object(raw);
      const rowFields = ['row_id', 'amount', 'raw_amount', 'raw_category_label', 'raw_transaction_label', 'lineage'];
      if (Object.keys(row).length !== rowFields.length || rowFields.some(key => !Object.hasOwn(row, key))) refuse();
      if (!text(row.row_id) || rowIds.has(row.row_id) || cents(row.amount) !== cents(row.raw_amount)) refuse();
      rowIds.add(row.row_id);
      for (const label of [row.raw_category_label, row.raw_transaction_label]) if (label !== null && typeof label !== 'string') refuse();
      const lineage = object(row.lineage);
      const lineageFields = ['source_file', 'sheet', 'row_number', 'raw_hash', 'run_id', 'mapping_version'];
      if (Object.keys(lineage).length !== lineageFields.length || lineageFields.some(key => !Object.hasOwn(lineage, key))) refuse();
      if (![lineage.source_file, lineage.run_id, lineage.mapping_version].every(text) || !Number.isSafeInteger(lineage.row_number) || (lineage.row_number as number) < 1 || typeof lineage.raw_hash !== 'string' || !/^[a-f0-9]{64}$/.test(lineage.raw_hash)) refuse();
      if (lineage.sheet !== null && !text(lineage.sheet)) refuse();
    }
    if (p.control_total !== null) cents(p.control_total);
  });
  const activeReceipts = (v.receipts as LedgerReceipt[]).filter(r => r.state === 'active');
  if (activeReceipts.length !== active.length) refuse();
  const conflictReceipts = (v.receipts as LedgerReceipt[]).filter(r => r.state === 'conflict');
  if (conflictReceipts.length !== conflicts.length) refuse();
  function matchesRevision(review: FinanceReview, receipt: LedgerReceipt): boolean {
    const index = (v.receipts as LedgerReceipt[]).indexOf(receipt);
    const revision = (v.revisions as Record<string, unknown>[])[index];
    const controlMatches = revision.control_total === null
      ? review.control_total === null
      : review.control_total !== null && cents(revision.control_total) === cents(review.control_total);
    if (JSON.stringify(receipt.logical_key) !== JSON.stringify([review.agency_id, review.carrier, review.period, review.statement_id]) || receipt.revision_id !== review.revision_id || revision.content_sha256 !== review.content_sha256 || !controlMatches) return false;
    const rows = revision.rows as Record<string, unknown>[];
    return rows.length === review.rows.length && rows.every((row, rowIndex) => {
      const classified = review.rows[rowIndex];
      const lineage = row.lineage as Record<string, unknown>;
      const source = classified.lineage;
      const sameLineage = lineage.source_file === source.source_file && lineage.sheet === source.sheet && lineage.row_number === source.row_number && lineage.raw_hash === source.raw_hash && lineage.run_id === source.run_id && lineage.mapping_version === source.mapping_version;
      return row.row_id === classified.row_id && cents(row.amount) === cents(classified.amount) && row.raw_amount === classified.raw_amount && row.raw_category_label === classified.raw_category_label && row.raw_transaction_label === classified.raw_transaction_label && sameLineage;
    });
  }
  const matchedActive = new Set<LedgerReceipt>();
  for (const review of active) {
    const receipt = activeReceipts.find(candidate => !matchedActive.has(candidate) && matchesRevision(review, candidate));
    if (!receipt) refuse();
    matchedActive.add(receipt);
  }
  if (conflicts.some((review, index) => !matchesRevision(review, conflictReceipts[index]))) refuse();
  const groups = new Set<string>();
  for (const item of v.grouped_totals as unknown[]) {
    const g = object(item);
    const totalFields = ['agency_id', 'carrier', 'period', 'category_totals', 'statement_total'];
    if (Object.keys(g).length !== totalFields.length || totalFields.some(key => !Object.hasOwn(g, key))) refuse();
    if (![g.agency_id, g.carrier, g.period].every(text)) refuse();
    const key = JSON.stringify([g.agency_id, g.carrier, g.period]);
    if (groups.has(key)) refuse();
    groups.add(key);
    const reviews = active.filter(r => r.agency_id === g.agency_id && r.carrier === g.carrier && r.period === g.period);
    if (!reviews.length) refuse();
    const totals = object(g.category_totals);
    if (Object.keys(totals).length !== CATEGORIES.length) refuse();
    let sum = BigInt(0);
    for (const category of CATEGORIES) {
      const amount = cents(totals[category]);
      if (amount !== reviews.reduce((n, r) => n + cents(r.category_totals[category]), BigInt(0))) refuse();
      sum += amount;
    }
    if (sum !== cents(g.statement_total)) refuse();
  }
  if (active.some(r => !groups.has(JSON.stringify([r.agency_id, r.carrier, r.period])))) refuse();
  // The engine decides whether a conflict is still unresolved. This display
  // boundary checks amounts and scope without replaying that decision process.
  const conflictScopes = new Set(conflicts.map(review => JSON.stringify([review.agency_id, review.carrier, review.period])));
  const seenConflictGroups = new Set<string>();
  for (const item of v.unresolved_conflict_totals as unknown[]) {
    const g = object(item);
    const totalFields = ['agency_id', 'carrier', 'period', 'category_totals', 'statement_total'];
    if (Object.keys(g).length !== totalFields.length || totalFields.some(key => !Object.hasOwn(g, key))) refuse();
    if (![g.agency_id, g.carrier, g.period].every(text)) refuse();
    const key = JSON.stringify([g.agency_id, g.carrier, g.period]);
    if (seenConflictGroups.has(key)) refuse();
    seenConflictGroups.add(key);
    if (!conflictScopes.has(key)) refuse();
    const totals = object(g.category_totals);
    if (Object.keys(totals).length !== CATEGORIES.length) refuse();
    if (CATEGORIES.reduce((n, c) => n + cents(totals[c]), BigInt(0)) !== cents(g.statement_total)) refuse();
  }
  return value as FinanceLedger;
}
