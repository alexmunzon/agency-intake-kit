// Weekly watch for braces GHSA-vfj7-8cjw-p6xm (see SECURITY.md, Known dependency risk).
// Exit 0 while the advisory is unchanged and unpatched. Exit 1 when a fix ships, the advisory is
// withdrawn or changes, or the check cannot run, so the scheduled workflow fails and GitHub emails
// the owner. Read-only: one public API call, no token required, nothing written.

import { pathToFileURL } from "node:url";

export const ADVISORY_ID = "GHSA-vfj7-8cjw-p6xm";
const KNOWN_RANGE = "<= 3.0.3";
const NEXT_STEP =
  "Update braces in all three repos with full checks, then change SECURITY.md from partly removed to patched.";

export function assess(advisory) {
  if (advisory?.withdrawn_at) {
    return { ok: false, message: `${ADVISORY_ID} was withdrawn on ${advisory.withdrawn_at}. Review SECURITY.md.` };
  }
  const entry = Array.isArray(advisory?.vulnerabilities)
    ? advisory.vulnerabilities.find((v) => v?.package?.ecosystem === "npm" && v?.package?.name === "braces")
    : undefined;
  if (!entry) {
    return { ok: false, message: `${ADVISORY_ID} response has no npm braces entry. Check the advisory by hand.` };
  }
  if (entry.first_patched_version) {
    return { ok: false, message: `braces ${entry.first_patched_version} patches ${ADVISORY_ID}. ${NEXT_STEP}` };
  }
  if (entry.vulnerable_version_range !== KNOWN_RANGE) {
    return {
      ok: false,
      message: `${ADVISORY_ID} affected range changed from "${KNOWN_RANGE}" to "${entry.vulnerable_version_range}". Recheck installed versions.`,
    };
  }
  return { ok: true, message: `${ADVISORY_ID}: braces ${KNOWN_RANGE} affected, no patched release yet.` };
}

async function main() {
  try {
    const response = await fetch(`https://api.github.com/advisories/${ADVISORY_ID}`, {
      headers: { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`GitHub API returned ${response.status}`);
    const result = assess(await response.json());
    console.log(result.message);
    process.exitCode = result.ok ? 0 : 1;
  } catch (error) {
    console.error(`Could not check ${ADVISORY_ID}: ${error.message}`);
    process.exitCode = 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) await main();
