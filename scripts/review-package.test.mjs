import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildReviewPackage } from './review-package.mjs';

test('packages exact committed synthetic Intake bytes without combining demos', async () => {
 const p = await buildReviewPackage(new URL('../dashboard/public/demo-run', import.meta.url), 'synthetic-agency-a');
 assert.equal(p.intake_run_id, 'demo'); assert.equal(p.artifacts.length, 4);
 assert.ok(p.artifacts.every(a => Buffer.byteLength(a.content) === a.size_bytes));
});
test('refuses path escape and absent explicit agency', async () => {
 await assert.rejects(buildReviewPackage('dashboard/public/demo-run', 'example', ['../demo-finance.json']), /Unsafe/);
 await assert.rejects(buildReviewPackage('dashboard/public/demo-run', ''), /Explicit/);
});
