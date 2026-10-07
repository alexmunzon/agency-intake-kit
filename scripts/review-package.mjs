// Read-only packaging of an explicitly synthetic Intake snapshot for /package.
import { readFile, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export async function buildReviewPackage(root, agencyId, extraPaths = []) {
  if (!agencyId?.trim()) throw new Error('Explicit synthetic agency ID required');
  const base = await realpath(root);
  const paths = new Set(['manifest.json', 'scorecard.json', 'exceptions.jsonl', 'rts_coverage.json', ...extraPaths]);
  const artifacts = [];
  for (const path of paths) {
    if (isAbsolute(path) || path.split('/').some(p => !p || p === '.' || p === '..') || path.includes('\\')) throw new Error('Unsafe artifact path');
    const actual = await realpath(resolve(base, path));
    const rel = relative(base, actual);
    if (rel.startsWith('..') || isAbsolute(rel)) throw new Error('Artifact escapes snapshot root');
    const bytes = await readFile(actual);
    const content = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    artifacts.push({ path, sha256: createHash('sha256').update(bytes).digest('hex'), size_bytes: bytes.length, content });
  }
  const manifest = JSON.parse(artifacts.find(a => a.path === 'manifest.json').content);
  if (typeof manifest.run_id !== 'string' || !manifest.run_id.trim()) throw new Error('Manifest has no run ID');
  return { schema_version: 'review-package-1', data_kind: 'synthetic', agency_id: agencyId, intake_run_id: manifest.run_id, artifacts };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [root, agencyId, attestation, ...extraPaths] = process.argv.slice(2);
  if (!root || !agencyId || attestation !== '--synthetic') throw new Error('Usage: node scripts/review-package.mjs ROOT AGENCY_ID --synthetic [EXTRA_RELATIVE_PATHS...]');
  process.stdout.write(JSON.stringify(await buildReviewPackage(root, agencyId, extraPaths)) + '\n');
}
