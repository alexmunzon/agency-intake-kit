import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReviewPackageSummary } from '../review-package';
function valid() {
 return JSON.stringify({ schema_version: 'review-package-1', data_kind: 'synthetic', agency_id: 'example-agency', intake_run_id: 'demo', artifacts: ['manifest.json', 'scorecard.json', 'exceptions.jsonl', 'rts_coverage.json'].map(path => { const content = readFileSync(`public/demo-run/${path}`, 'utf8'); return { path, content, size_bytes: new TextEncoder().encode(content).length, sha256: createHash('sha256').update(content).digest('hex') }; }) });
}
function select(source: string | Promise<string>) {
 fireEvent.change(screen.getByLabelText('Import review package'), { target: { files: [{ size: 100, text: () => Promise.resolve(source) }] } });
}
describe('review summary replacement', () => {
 it('preserves the last valid view after malformed replacement and supports clear', async () => {
  render(<ReviewPackageSummary />); select(valid());
  await screen.findByText(/Loaded agency example-agency/);
  select('{broken');
  await screen.findByRole('alert');
  expect(screen.getByText(/Loaded agency example-agency/)).toBeInTheDocument();
  expect(screen.getByText('Accepted clean output rows: 12833')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear summary' }));
  expect(screen.getByText(/No package loaded/)).toBeInTheDocument();
 });
 it('does not resurrect a cleared view when an earlier import finishes', async () => {
  render(<ReviewPackageSummary />); let release!: (x: string) => void;
  select(new Promise<string>(resolve => { release = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: 'Clear summary' })); release(valid());
  await waitFor(() => expect(screen.queryByText(/Loaded agency/)).toBeNull());
  expect(screen.getByText(/No package loaded/)).toBeInTheDocument();
 });
});
