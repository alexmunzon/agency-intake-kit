import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReviewPackageSummary } from '../review-package';

const example = readFileSync('public/demo-review-package.json', 'utf8');
function valid() {
  return JSON.stringify({ ...JSON.parse(example), agency_id: 'example-agency' });
}
function select(source: string | Promise<string>) {
  fireEvent.change(screen.getByLabelText('Import review package'), { target: { files: [{ size: 100, text: () => Promise.resolve(source) }] } });
}
function changed() {
  const data = JSON.parse(example);
  const manifest = data.artifacts[0];
  manifest.content = JSON.stringify({ ...JSON.parse(manifest.content), engine_version: 'changed' });
  manifest.size_bytes = new TextEncoder().encode(manifest.content).length;
  manifest.sha256 = createHash('sha256').update(manifest.content).digest('hex');
  return JSON.stringify(data);
}
afterEach(() => vi.unstubAllGlobals());
describe('review summary replacement', () => {
  it('starts empty with Clear disabled and loads the committed synthetic sample through validation', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, text: async () => example });
    vi.stubGlobal('fetch', fetcher);
    render(<ReviewPackageSummary />);
    expect(screen.getByRole('button', { name: 'Clear summary' })).toBeDisabled();
    expect(screen.getByText('Accepted clean output rows: Unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await screen.findByText(/Loaded agency synthetic-agency-a/);
    expect(fetcher).toHaveBeenCalledWith('/demo-review-package.json');
    expect(screen.getByText('Accepted clean output rows: 12836')).toBeInTheDocument();
    expect(screen.getByText('Unavailable: no run-bound expected source inventory')).toBeInTheDocument();
    expect(screen.getByText('Unavailable: no bound identity partition')).toBeInTheDocument();
    expect(screen.getByText('Unavailable: no bound finance review')).toBeInTheDocument();
    expect(screen.getByText('Identity groups without declared approval: Unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear summary' })).toBeEnabled();
    const provenance = screen.getByText('Verified artifact provenance').closest('details')!;
    expect(provenance.open).toBe(false);
    fireEvent.click(screen.getByText('Verified artifact provenance'));
    expect(provenance.open).toBe(true);
    expect(screen.getByText('manifest.json')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Load synthetic example' })).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('preserves the last valid view after malformed replacement and supports clear', async () => {
    render(<ReviewPackageSummary />); select(valid());
    await screen.findByText(/Loaded agency example-agency/);
    select('{broken');
    await screen.findByRole('alert');
    expect(screen.getByText(/Loaded agency example-agency/)).toBeInTheDocument();
    expect(screen.getByText('Accepted clean output rows: 12836')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear summary' }));
    expect(screen.getByText(/No package loaded/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear summary' })).toBeDisabled();
    expect(screen.getByText('Accepted clean output rows: Unavailable')).toBeInTheDocument();
  });

  it('keeps Clear disabled while empty and cancels an initial in-flight import', async () => {
    render(<ReviewPackageSummary />); let release!: (x: string) => void;
    select(new Promise<string>(resolve => { release = resolve; }));
    expect(screen.getByRole('button', { name: 'Clear summary' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel loading' }));
    await act(async () => release(valid()));
    await waitFor(() => expect(screen.queryByText(/Loaded agency/)).toBeNull());
    expect(screen.getByText(/No package loaded/)).toBeInTheDocument();
  });

  it('does not resurrect a cleared valid snapshot after an older replacement finishes', async () => {
    render(<ReviewPackageSummary />); select(valid());
    await screen.findByText(/Loaded agency example-agency/);
    let release!: (x: string) => void;
    select(new Promise<string>(resolve => { release = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear summary' }));
    await act(async () => release(valid()));
    expect(screen.getByText(/No package loaded/)).toBeInTheDocument();
    expect(screen.queryByText(/Loaded agency/)).not.toBeInTheDocument();
  });

  it('refuses corrupted sample hashes through the same boundary as uploaded files', async () => {
    const corrupt = JSON.parse(example);
    corrupt.artifacts[0].sha256 = '0'.repeat(64);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(corrupt) }));
    render(<ReviewPackageSummary />); select(valid());
    await screen.findByText(/Loaded agency example-agency/);
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Stale artifact hash');
    expect(screen.getByText(/Loaded agency example-agency/)).toBeInTheDocument();
  });

  it('preserves same-run pins for both sample and file replacement until explicitly cleared', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => example }));
    render(<ReviewPackageSummary />); select(changed());
    await screen.findByText(/Loaded agency synthetic-agency-a/);
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('changed or disappeared');
    fireEvent.click(screen.getByRole('button', { name: 'Clear summary' }));
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await screen.findByText(/Loaded agency synthetic-agency-a/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps missing evidence unknown if the example is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(<ReviewPackageSummary />);
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic example unavailable');
    expect(screen.getByText('Accepted clean output rows: Unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear summary' })).toBeDisabled();
  });
});
