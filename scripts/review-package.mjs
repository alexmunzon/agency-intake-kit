// Read-only packaging of an explicitly synthetic Intake snapshot for /package.
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

function readSnapshot(root, paths) {
  return new Promise((resolveRead, reject) => {
    const child = spawn('python3', [fileURLToPath(new URL('./review-package-read.py', import.meta.url))], { stdio: ['pipe', 'pipe', 'pipe'] });
    const chunks = []; let length = 0, error = '';
    child.stdout.on('data', chunk => { length += chunk.length; if (length > 80_000_000) child.kill(); else chunks.push(chunk); });
    child.stderr.on('data', chunk => { error = (error + chunk.toString()).slice(0, 2048); });
    child.on('error', reject);
    child.on('close', code => { if (code !== 0) reject(new Error(error.trim() || 'Safe snapshot reader failed')); else { try { resolveRead(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch (e) { reject(e); } } });
    child.stdin.on('error', reject);
    child.stdin.end(JSON.stringify({ root: root instanceof URL ? fileURLToPath(root) : resolve(root), paths }));
  });
}

export async function buildReviewPackage(root, agencyId, extraPaths = []) {
  if (!agencyId?.trim()) throw new Error('Explicit synthetic agency ID required');
  const paths = [...new Set(['manifest.json', 'scorecard.json', 'exceptions.jsonl', 'rts_coverage.json', ...extraPaths])];
  const artifacts = await readSnapshot(root, paths);
  const manifest = JSON.parse(artifacts.find(a => a.path === 'manifest.json').content);
  if (typeof manifest.run_id !== 'string' || !manifest.run_id.trim()) throw new Error('Manifest has no run ID');
  return { schema_version: 'review-package-1', data_kind: 'synthetic', agency_id: agencyId, intake_run_id: manifest.run_id, artifacts };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [root, agencyId, attestation, ...extraPaths] = process.argv.slice(2);
  if (!root || !agencyId || attestation !== '--synthetic') throw new Error('Usage: node scripts/review-package.mjs ROOT AGENCY_ID --synthetic [EXTRA_RELATIVE_PATHS...]');
  process.stdout.write(JSON.stringify(await buildReviewPackage(root, agencyId, extraPaths)) + '\n');
}
