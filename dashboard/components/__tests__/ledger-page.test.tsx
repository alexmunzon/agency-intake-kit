import { readFileSync } from 'node:fs';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LedgerPage from '@/app/ledger/page';

const source = readFileSync('public/demo-ledger.json', 'utf8');
afterEach(() => vi.unstubAllGlobals());
async function loadExample() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => source }));
  render(<LedgerPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
  await screen.findByRole('group', { name: 'Signed active total' });
}
function history() { return screen.getByText('Receipt history and evidence (3)'); }

it('matches the navigation heading and keeps one page main landmark', () => {
  const { container } = render(<main><LedgerPage /></main>);
  expect(container.querySelectorAll('main')).toHaveLength(1);
  expect(screen.getByRole('region', { name: 'Revenue breakdown' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Revenue breakdown');
  expect(screen.getByText(/No ledger loaded/)).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: 'Signed active total' })).not.toBeInTheDocument();
  expect(screen.getByText(/does not provide hosted persistence/).closest('details')).not.toHaveAttribute('open');
  expect(screen.getByText('Read-only review. No authenticated approval or accounting posting.')).toBeVisible();
});

it('leads with exact signed active and unclassified totals, then categories and source rows before history', async () => {
  await loadExample();
  const total = screen.getByRole('group', { name: 'Signed active total' });
  const unclassified = screen.getByRole('group', { name: 'Unclassified amount' });
  expect(total).toHaveTextContent('85.03');
  expect(unclassified).toHaveTextContent('0.03');
  const categories = screen.getByRole('region', { name: 'Category totals for synthetic-september' });
  const rows = screen.getByRole('region', { name: 'Source rows for synthetic-september' });
  expect(within(rows).getByText('-25.00')).toBeInTheDocument();
  for (const before of [total, unclassified, categories, rows]) {
    expect(before.compareDocumentPosition(history()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
  expect(history().tagName).toBe('SUMMARY');
  expect(history().closest('details')).not.toHaveAttribute('open');
  expect(screen.getByRole('region', { name: 'Receipt history' })).not.toBeVisible();
  expect(screen.getByText(/Unclassified amounts remain in the statement total/)).toBeVisible();
  expect(screen.getByText(/Statement content hash/).closest('details')).not.toHaveAttribute('open');
});

it('loads retained duplicate and superseded history and preserves it after invalid replacement', async () => {
  await loadExample();
  fireEvent.click(history());
  const receipts = screen.getByRole('region', { name: 'Receipt history' });
  expect(receipts).toHaveAttribute('tabindex', '0');
  expect(within(receipts).getByText('superseded')).toBeVisible();
  expect(within(receipts).getAllByText('duplicate')).toHaveLength(2);
  expect(within(receipts).getByText('Oct 7, 2026, 12:00:00 AM UTC')).toHaveAttribute('datetime', '2026-10-07T00:00:00Z');
  const firstTimestamp = within(receipts).getAllByText('Exact timestamp')[0];
  fireEvent.click(firstTimestamp);
  expect(within(receipts).getByText('2026-10-07T00:00:00Z')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Open ledger JSON'), { target: { files: [{ size: 20, text: async () => '{bad json' }] } });
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('previous valid ledger'));
  expect(within(receipts).getByText('superseded')).toBeVisible();
  expect(screen.getByRole('group', { name: 'Signed active total' })).toHaveTextContent('85.03');
  fireEvent.click(history());
  expect(screen.getByRole('region', { name: 'Receipt history' })).not.toBeVisible();
});

it('supports repeated example loads without doubling receipts or changing signed totals', async () => {
  await loadExample();
  fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('group', { name: 'Signed active total' })).toHaveTextContent('85.03');
  expect(screen.getAllByText('Receipt history and evidence (3)')).toHaveLength(1);
});

it('does not present absent active amounts as zero', async () => {
  render(<LedgerPage />);
  const empty = JSON.stringify({ schema_version: 1, artifact_type: 'neutral_finance_ledger', receipts: [], revisions: [], active_reviews: [], conflicts: [], grouped_totals: [], unresolved_conflict_totals: [] });
  fireEvent.change(screen.getByLabelText('Open ledger JSON'), { target: { files: [{ size: empty.length, text: async () => empty }] } });
  await screen.findByText('No active revenue supplied.');
  expect(screen.queryByRole('group', { name: 'Signed active total' })).not.toBeInTheDocument();
  expect(screen.queryByRole('group', { name: 'Unclassified amount' })).not.toBeInTheDocument();
});

it('ignores an older example response after a newer import fails', async () => {
  let resolveResponse!: (value: { ok: boolean; text: () => Promise<string> }) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { resolveResponse = resolve; })));
  render(<LedgerPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
  fireEvent.change(screen.getByLabelText('Open ledger JSON'), { target: { files: [{ size: 20, text: async () => '{bad json' }] } });
  await screen.findByRole('alert');
  await act(async () => resolveResponse({ ok: true, text: async () => source }));
  expect(screen.getByText(/No ledger loaded/)).toBeInTheDocument();
  expect(screen.queryByText('superseded')).not.toBeInTheDocument();
});
