import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SourceReadiness } from '../source-readiness';
import { parseReadiness } from '@/lib/source-readiness';
const fixture = (name: string) => readFileSync(resolve('../fixtures/source-readiness', `${name}.json`), 'utf8');
async function loadSource(source: string) {
  fireEvent.change(screen.getByLabelText('Package JSON'), { target: { value: source } });
  fireEvent.click(screen.getByRole('button', { name: 'Validate and load JSON' }));
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
}
async function load(name: string) {
  await loadSource(fixture(name));
  await screen.findByText('Agency: agency-synthetic');
}
describe('readiness page', () => {
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it('starts unknown with no completion claim', () => {
    render(<SourceReadiness />);
    expect(screen.getByText('Readiness unknown')).toBeInTheDocument();
    expect(screen.queryByText('Expected coverage complete')).not.toBeInTheDocument();
    expect(screen.getByText(/Browser memory only/).closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Download a package to keep your edits. Refreshing or leaving this page clears them.")).toBeVisible();
    expect(screen.queryByText("Synthetic data only · Source readiness")).not.toBeInTheDocument();
  });
  it('keeps valid state after malformed or stale-hash import', async () => {
    render(<SourceReadiness />);
    await load('current');
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Package JSON'), { target: { value: '{bad' } });
    fireEvent.click(screen.getByRole('button', { name: 'Validate and load JSON' }));
    await screen.findByRole('alert');
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
    expect(screen.getByText('Agency: agency-synthetic')).toBeInTheDocument();
    const changedEvidence = JSON.parse(fixture('current'));
    changedEvidence.evidence[0].content = 'altered bytes';
    fireEvent.change(screen.getByLabelText('Package JSON'), { target: { value: JSON.stringify(changedEvidence) } });
    fireEvent.click(screen.getByRole('button', { name: 'Validate and load JSON' }));
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
  });
  it('exposes all five states with receipts and ownership', async () => {
    render(<SourceReadiness />);
    await load('demo');
    for (const state of ['missing', 'stale', 'current', 'conflicting', 'unknown']) {
      expect(screen.getByRole('heading', { name: new RegExp(`${state} · Harborline`) })).toBeInTheDocument();
    }
    expect(screen.getByText('Duplicate deliveries retained: 1')).toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText('Owner')[0], { target: { value: 'Synthetic onboarding' } });
    expect(screen.getAllByLabelText('Owner')[0]).toHaveValue('Synthetic onboarding');
    fireEvent.click(screen.getByRole('button', { name: 'Clear local view' }));
    await waitFor(() => expect(screen.getByText('Readiness unknown')).toBeInTheDocument());
    expect(screen.queryByText('Agency: agency-synthetic')).not.toBeInTheDocument();
  });
  it.each(['rewritten version', 'rewritten receipt', 'removed receipt'])('retains the previous view after a valid same-run package with %s', async kind => {
    render(<SourceReadiness />);
    await load('current');
    const incoming = JSON.parse(fixture('current'));
    if (kind === 'rewritten version') incoming.versions[0].file_name = 'rewritten.csv';
    if (kind === 'rewritten receipt') incoming.receipts[0].owner = 'Rewritten history';
    if (kind === 'removed receipt') incoming.receipts = [];
    await loadSource(JSON.stringify(incoming));
    expect(screen.getByRole('alert')).toHaveTextContent(/changed\/removed history/);
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
    expect(screen.getByText('Receipts retained: 1')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Version and receipt evidence' })).queryByText(/rewritten.csv|Rewritten history/)).not.toBeInTheDocument();
  });
  it('preserves edited planning fields on rejected imports and disables editing during validation', async () => {
    render(<SourceReadiness />);
    await load('current');
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'Edited onboarding owner' } });
    fireEvent.change(screen.getByLabelText('Next action'), { target: { value: 'Keep this pending review' } });
    const incoming = JSON.parse(fixture('current'));
    incoming.receipts = [];
    let finish!: (value: string) => void;
    const pending = new Promise<string>(resolve => { finish = resolve; });
    fireEvent.change(screen.getByLabelText('Import synthetic package'), { target: { files: [{ name: 'rollback.json', text: () => pending }] } });
    expect(screen.getByLabelText('Owner')).toBeDisabled();
    expect(screen.getByLabelText('Next action')).toBeDisabled();
    await act(async () => { finish(JSON.stringify(incoming)); await pending; });
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('Owner')).toHaveValue('Edited onboarding owner');
    expect(screen.getByLabelText('Next action')).toHaveValue('Keep this pending review');
    expect(screen.getByLabelText('Owner')).not.toBeDisabled();
    expect(screen.getByLabelText('Next action')).not.toBeDisabled();
  });
  it('accepts same-run idempotent imports and appended correction/duplicate history', async () => {
    render(<SourceReadiness />);
    await load('current');
    await load('current');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    const incoming = JSON.parse(fixture('corrected'));
    incoming.receipts.push({ ...incoming.receipts[0], receipt_id: 'r-duplicate' });
    await loadSource(JSON.stringify(incoming));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
    expect(screen.getByText('Receipts retained: 3')).toBeInTheDocument();
    expect(screen.getByText('Duplicate deliveries retained: 1')).toBeInTheDocument();
    expect(screen.getByText(/v1 · statement.csv · Superseded/)).toBeInTheDocument();
  });
  it('allows a fresh same-run snapshot after clearing the local view', async () => {
    render(<SourceReadiness />);
    await load('current');
    fireEvent.click(screen.getByRole('button', { name: 'Clear local view' }));
    await load('missing');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Readiness missing')).toBeInTheDocument();
    expect(screen.getByText('Receipts retained: 0')).toBeInTheDocument();
  });
  it('keeps cleared memory empty when a pending import finishes', async () => {
    render(<SourceReadiness />);
    await load('current');
    const digest = vi.spyOn(crypto.subtle, 'digest');
    let finish!: (value: string) => void;
    const pending = new Promise<string>(resolve => { finish = resolve; });
    const file = { name: 'pending.json', text: () => pending };
    fireEvent.change(screen.getByLabelText('Import synthetic package'), { target: { files: [file] } });
    expect(screen.getByRole('status')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear local view' }));
    await act(async () => {
      finish(fixture('missing')); await pending;
      await waitFor(() => expect(digest).toHaveBeenCalledOnce());
      await digest.mock.results.at(-1)!.value;
    });
    expect(screen.getByText('Readiness unknown')).toBeInTheDocument();
    expect(screen.queryByText('Agency: agency-synthetic')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('does not let an older pending import overwrite a later loaded package', async () => {
    render(<SourceReadiness />);
    let finish!: (value: string) => void;
    const pending = new Promise<string>(resolve => { finish = resolve; });
    vi.stubGlobal('fetch', vi.fn(() => pending.then(text => ({ ok: true, text: async () => text }))));
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear local view' }));
    await load('current');
    const digest = vi.spyOn(crypto.subtle, 'digest');
    await act(async () => {
      finish(fixture('missing')); await pending;
      await waitFor(() => expect(digest).toHaveBeenCalledOnce());
      await digest.mock.results.at(-1)!.value;
    });
    expect(screen.getByText('Expected coverage complete')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('does not show an obsolete failure after clearing', async () => {
    render(<SourceReadiness />);
    let fail!: (error: Error) => void;
    const pending = new Promise<string>((_, reject) => { fail = reject; });
    fireEvent.change(screen.getByLabelText('Import synthetic package'), { target: { files: [{ name: 'bad.json', text: () => pending }] } });
    fireEvent.click(screen.getByRole('button', { name: 'Clear local view' }));
    await act(async () => { fail(new Error('read failed')); await pending.catch(() => {}); });
    expect(screen.getByText('Readiness unknown')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('downloads a valid reusable package preserving owner/action edits and evidence', async () => {
    render(<SourceReadiness />);
    await load('corrected');
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'Synthetic reviewer' } });
    fireEvent.change(screen.getByLabelText('Next action'), { target: { value: 'Verify the named correction' } });
    let downloaded!: Blob;
    const originalURL = URL;
    class DownloadURL extends originalURL {
      static createObjectURL = vi.fn((blob: Blob) => { downloaded = blob; return 'blob:readiness-test'; });
      static revokeObjectURL = vi.fn();
    }
    vi.stubGlobal('URL', DownloadURL);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button', { name: 'Download reusable package' }));
    expect(click).toHaveBeenCalledOnce();
    const anchor = click.mock.instances[0] as HTMLAnchorElement;
    expect(anchor.download).toBe('source_readiness.json');
    vi.runAllTimers();
    expect(DownloadURL.revokeObjectURL).toHaveBeenCalledWith('blob:readiness-test');
    vi.useRealTimers();
    const source = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(reader.result as string); reader.onerror = reject; reader.readAsText(downloaded);
    });
    const saved = await parseReadiness(source);
    expect(saved.expected_inventory![0].owner).toBe('Synthetic reviewer');
    expect(saved.expected_inventory![0].next_action).toBe('Verify the named correction');
    expect(saved.receipts).toHaveLength(2);
    expect(saved.versions[1].supersedes_version_id).toBe('v1');
    expect(saved.evidence).toEqual(JSON.parse(fixture('corrected')).evidence);
    expect(saved.intake_run_id).toBeNull();
  });
});
