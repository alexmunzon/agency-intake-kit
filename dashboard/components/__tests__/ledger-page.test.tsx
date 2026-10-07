import { readFileSync } from 'node:fs';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LedgerPage from '@/app/ledger/page';
const source = readFileSync('public/demo-ledger.json', 'utf8');
afterEach(() => vi.unstubAllGlobals());
it('uses one page main landmark when rendered inside the shared layout', () => {
  const {container} = render(<main><LedgerPage /></main>);
  expect(container.querySelectorAll('main')).toHaveLength(1);
  expect(screen.getByRole('region', {name: 'Receipt ledger'})).toBeInTheDocument();
});
it('loads exported history and retains the valid view after a rejected import', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, text: async () => source}));
  render(<LedgerPage />);
  expect(screen.getByText(/does not provide hosted persistence/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'Load synthetic example'}));
  await screen.findByText('superseded');
  expect(screen.getAllByText('duplicate')).toHaveLength(2);
  const file = {size: 20, text: async () => '{bad json'};
  fireEvent.change(screen.getByLabelText('Open ledger JSON'), {target:{files:[file]}});
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('previous valid ledger'));
  expect(screen.getByText('superseded')).toBeInTheDocument();
}, 10000);

it('ignores an older example response after a newer import fails', async () => {
  let resolveResponse!: (value: {ok: boolean; text: () => Promise<string>}) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { resolveResponse = resolve; })));
  render(<LedgerPage />);
  fireEvent.click(screen.getByRole('button', {name: 'Load synthetic example'}));
  fireEvent.change(screen.getByLabelText('Open ledger JSON'), {target: {files: [{size: 20, text: async () => '{bad json'}]}});
  await screen.findByRole('alert');
  await act(async () => resolveResponse({ok: true, text: async () => source}));
  expect(screen.getByText(/No ledger loaded/)).toBeInTheDocument();
  expect(screen.queryByText('superseded')).not.toBeInTheDocument();
}, 10000);
