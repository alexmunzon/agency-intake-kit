import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parseFinanceLedger } from '../finance-ledger';

const source = readFileSync('public/demo-ledger.json', 'utf8');
describe('ledger export boundary', () => {
  it('retains correction and duplicate history with exact signed totals', () => {
    const ledger = parseFinanceLedger(source);
    expect(ledger.receipts.map(r => r.state)).toEqual(['superseded', 'duplicate', 'active']);
    expect(ledger.grouped_totals[0].statement_total).toBe('85.03');
    expect(ledger.grouped_totals[0].category_totals.unclassified).toBe('0.03');
    expect(ledger.active_reviews[0].rows[1].amount).toBe('-25.00');
  });
  it.each(['total', 'receipt', 'mapping', 'unknown', 'duplicate-key'])('refuses %s corruption', kind => {
    const data = JSON.parse(source);
    if (kind === 'total') data.grouped_totals[0].statement_total = '0.00';
    if (kind === 'receipt') data.receipts[2].receipt_id = data.receipts[0].receipt_id;
    if (kind === 'mapping') data.active_reviews[0].rows[2].category = 'renewal';
    if (kind === 'unknown') data.schema_version = 99;
    const text = kind === 'duplicate-key' ? JSON.stringify(data).replace('"schema_version":1', '"schema_version":1,"schema_version":1') : JSON.stringify(data);
    expect(() => parseFinanceLedger(text)).toThrow();
  });
  it('refuses a classified active row that contradicts its retained revision', () => {
    const data = JSON.parse(source);
    data.active_reviews[0].rows[0].amount = '111.00';
    data.active_reviews[0].rows[0].raw_amount = '111.00';
    data.active_reviews[0].category_totals.renewal = '86.00';
    data.active_reviews[0].statement_total = '86.03';
    data.grouped_totals[0].category_totals.renewal = '86.00';
    data.grouped_totals[0].statement_total = '86.03';
    expect(() => parseFinanceLedger(JSON.stringify(data))).toThrow();
  });
  it('accepts equivalent retained lineage with a different object key order', () => {
    const data = JSON.parse(source);
    const lineage = data.revisions[2].rows[0].lineage;
    data.revisions[2].rows[0].lineage = Object.fromEntries(Object.entries(lineage).reverse());
    expect(parseFinanceLedger(JSON.stringify(data)).active_reviews).toHaveLength(1);
  });
  it('refuses conflict totals without retained conflict evidence', () => {
    const data = JSON.parse(source);
    data.unresolved_conflict_totals = data.grouped_totals;
    expect(() => parseFinanceLedger(JSON.stringify(data))).toThrow();
  });
  it('refuses missing or repeated active review coverage', () => {
    const data = JSON.parse(source);
    data.active_reviews = [];
    expect(() => parseFinanceLedger(JSON.stringify(data))).toThrow();
    data.active_reviews = [JSON.parse(source).active_reviews[0], JSON.parse(source).active_reviews[0]];
    data.receipts[0].state = 'active';
    expect(() => parseFinanceLedger(JSON.stringify(data))).toThrow();
  });
  it('accepts retained conflict evidence and checks its displayed total arithmetic', () => {
    const data = JSON.parse(source);
    const conflictReceipt = structuredClone(data.receipts[2]);
    conflictReceipt.receipt_id = 'late-conflict';
    conflictReceipt.received_at = '2026-10-07T00:00:03Z';
    conflictReceipt.revision_id = 'r3';
    conflictReceipt.replaces_revision_id = null;
    conflictReceipt.canonical_rows_sha256 = 'e'.repeat(64);
    conflictReceipt.state = 'conflict';
    conflictReceipt.reason = 'replacement_not_current';
    const revision = structuredClone(data.revisions[2]);
    revision.revision_id = 'r3';
    revision.content_sha256 = 'f'.repeat(64);
    revision.rows[0].amount = '120.00';
    revision.rows[0].raw_amount = '120.00';
    const review = structuredClone(data.active_reviews[0]);
    review.revision_id = 'r3';
    review.content_sha256 = revision.content_sha256;
    review.rows[0].amount = '120.00';
    review.rows[0].raw_amount = '120.00';
    review.category_totals.renewal = '95.00';
    review.statement_total = '95.03';
    const total = structuredClone(data.grouped_totals[0]);
    total.category_totals.renewal = '95.00';
    total.statement_total = '95.03';
    data.receipts.push(conflictReceipt);
    data.revisions.push(revision);
    data.conflicts.push(review);
    data.unresolved_conflict_totals.push(total);
    expect(parseFinanceLedger(JSON.stringify(data)).unresolved_conflict_totals[0].statement_total).toBe('95.03');
    total.statement_total = '95.04';
    expect(() => parseFinanceLedger(JSON.stringify(data))).toThrow();
  });
});

it('keeps exact scientific and plus-sign source amount notation', () => {
  const data = JSON.parse(source);
  data.revisions[0].rows[0].raw_amount = '+1e2';
  expect(parseFinanceLedger(JSON.stringify(data)).receipts).toHaveLength(3);
});
