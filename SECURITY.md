# Security

## Supported scope and reporting

This repository demonstrates data-validation and reconciliation practices using synthetic data. It is not a production service, a HIPAA certification or a security certification. Only the current demo tree is maintained; there is no promised response SLA or support for real agency records.

Report vulnerabilities privately to the repository maintainer, Alex Munzon, using [GitHub private vulnerability reporting](https://github.com/alexmunzon/agency-intake-kit/security/advisories/new) if enabled. Hosting settings were not verified in this review. If the form is unavailable, open an issue asking for a private reporting channel without exploit details, credentials or personal data. Include affected commit, synthetic reproduction, expected impact and proposed mitigation once a private channel is established. Never post a real credential or patient record.

## Threat boundaries

- **Inputs:** seeded synthetic demonstration material only. Do not put real client data, PHI, real SSNs or credentials into files, test fixtures, logs, issues, browser imports or model requests. Synthetic refusal-test values are not permission to process real identities. PII detection reduces exposure; it is not a guarantee that arbitrary sensitive input is safe.
- **Engine:** local files are processed into immutable run directories. Raw SSN and completeness gates precede model calls; rules control verdicts and models cannot override them. Corrections are new evidence, not silent edits. Use new output directories and preserve source files.
- **Models:** replay is the default and requires no credentials or live requests. Live/record modes can transmit minimized fields and incur charges; they require explicit approval and a separate review of destination, data and budget. Never disable gates to obtain a model answer.
- **Dashboard:** committed synthetic files are public. Run imports are parsed in the browser; the demo does not offer authenticated accounts, server uploads or private storage. Local browser processing is not approval to use real records on a public demo.
- **Build and CI:** dependency installation and build tools execute code. Use trusted sources and committed locks. CI uses read-only repository permissions, SHA-pinned actions and replay mode. These controls do not inspect GitHub account access, hosting authentication, security headers or branch protections.

## Known dependency risk

Reviewed **2026-10-06**: [braces GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) is a high-severity stack-exhaustion denial of service through deeply nested brace patterns. The GitHub-reviewed advisory affects versions through 3.0.3 and lists **no patched release**. The locked development-tool graph remains affected.

**Status: partly removed, not patched.** The shadcn package was the larger source of braces (four of five install paths). The app only used one stylesheet from it, so that file is now vendored unchanged at `dashboard/app/vendor/shadcn/tailwind.css` (from shadcn@4.21.1, sha256 `4c371f7a...2f0fae`, MIT license alongside) and the package is uninstalled. A test pins the file hash and fails if the package returns. The one remaining path is lint tooling: `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → braces 3.0.3, a development dependency that runs on maintainer machines and CI, not in the deployed site. That path is not patched; removing it would mean dropping Next's lint rules. Do not feed untrusted glob patterns to lint tooling. Avoid `npm audit fix --force` (it proposes an old, breaking shadcn) or speculative overrides; revisit when upstream ships a fix and rerun verification. A weekly workflow (`.github/workflows/braces-advisory.yml`, Mondays, also runnable by hand) reads the public advisory and fails, which emails the owner, when a patched release ships, the advisory is withdrawn or its affected range changes, or the check cannot run. It has read-only permissions and uses only the workflow's own built-in token. Two GitHub limits apply: scheduled workflows stop after 60 days without repository activity (re-enable them from the Actions tab), and the failure email goes to whoever last edited the schedule line, if their Actions notifications are on.

## Local review checklist

1. Review staged filenames first with `git diff --cached --name-only`. Environment files are ignored except the explicit `.env.example` template; ignoring a file does not remove an already tracked file. Never populate the template with real credentials. Review diffs and logs privately before sharing them.
2. For credential detection, use a maintained scanner against an explicitly bounded tracked-text snapshot, excluding environment contents. Redact output, disable credential-verification calls unless separately approved, and review candidates in context. Hashes and test sentinels are not automatically credentials. Do not treat a clean scan as proof about history, binaries or local files.
3. Recheck both locked npm scopes without changing dependencies:

   ```sh
   (cd dashboard && npm audit --package-lock-only --ignore-scripts --omit=dev)
   (cd dashboard && npm audit --package-lock-only --ignore-scripts)
   ```

   The full scope is expected to report the documented advisory until upstream fixes it. A nonzero audit exit can mean findings; distinguish it from network failure. Audit checks send package metadata to the configured npm registry, not source or environment contents.
4. Audit exact Python registry versions from `engine/uv.lock` with a maintained advisory scanner. Review exclusions separately. Advisory coverage does not prove dependency integrity, source-package safety or absence of unknown vulnerabilities.
5. Run `JEV_MODE=replay npm run verify` and record the commit, commands and results. Inspect the dependency diff before changing any lockfile; do not rotate secrets or rewrite Git history as part of an ordinary audit.

## Review evidence and limits

The 2026-10-06 bounded pre-hygiene review scanned 591 tracked UTF-8 text files out of 625 paths without reading environment contents. It found no convincing committed credential candidate after contextual review, and no known advisory among 56 locked Python registry packages. These are snapshot observations, not assurances about excluded files or future edits. After shadcn reclassification, the production-only locked npm audit returned zero findings; the full audit still returned nine affected package nodes representing the same underlying braces advisory. A production-only pass is not a runtime reachability proof. After the shadcn package was removed (2026-10-06), the production-only audit still returned zero findings and the full audit returned five affected package nodes, all on the lint path above.

Environment templates, binary/non-UTF-8 fixtures, Git history, other branches, untracked/ignored files, account settings, deployed controls and private runtime storage were outside the credential review. The review did not fuzz the application or certify privacy/compliance. Synthetic benchmark success is separate from security evidence. Before any real deployment, design and independently review authentication, authorization, retention, encryption, privacy, operational monitoring and incident response.
