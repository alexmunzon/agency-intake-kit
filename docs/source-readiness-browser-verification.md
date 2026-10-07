# Source readiness browser verification

Date: 2026-10-07. Local preview: `http://127.0.0.1:3122/readiness` in Codex in-app browser only. Synthetic evidence only. This is verification of an uncommitted working tree, not an exact-head, hosted or production check.

## Observed results

- Initial view: **pass**. The heading was `Readiness unknown`; copy said the inventory was absent or empty and completeness could not be established. Download was disabled.
- Load synthetic example: **pass**. All five states appeared: current, missing, stale, unknown, conflicting. Summary said `Readiness conflicting`, `1 of 5 expected files are current`, receipts retained 6, duplicate deliveries retained 1 and unexpected versions None.
- Owner/action typing: **pass**. The first Owner field retained `Browser verification owner`; the first Next action retained `Check evidence soon` after sequential character typing, blur and inspection. The initial long typing operation hit a browser command deadline after inserting a partial owner, but the next state showed those characters retained and short continuation completed the edit.
- Desktop width: **pass** at explicit 1440 by 1000 viewport. A read-only DOM measurement returned `innerWidth = 1440`, document scrollWidth 1440 and body scrollWidth 1440. The full-page JPEG is 1440 by 2020; visual inspection showed readable cards and no sideways overflow.

Screenshot: [Desktop synthetic example and retained edits](screenshots/readiness-desktop.jpg).

## Incomplete checks

The in-app browser timed out while opening the paste editor, reset the tool session, and then reported `Browser is not available: iab`. A surface inventory showed no in-app browser. No other browser was controlled.

The following remain **unverified** until that surface is restored: malformed paste import preserves previous package; reusable JSON download/reimport retains evidence and edits; corrections and source-version evidence details via fixture import; clearing the view; 375px mobile overflow and layout; browser console errors; final code after remaining hot reload changes. A click attempt is not a verified result.

The viewport override could not be reset after the browser became unavailable. Reset it on recovery before ending verification.

## Full verification gate

The separately running `/private/tmp/readiness-verify.log` was inspected without launching or stopping a suite. At last inspection, scripts had 6 passes; ruff check passed; 178 engine files were formatted; mypy passed for 103 source files; engine pytest was still in progress with dots and no final summary. The full gate has **not yet been confirmed green** by this evidence.

## Bounded recovery attempt after continuity review

Root review subsequently identified a same-package history replacement gap, and the engine/dashboard workers began adding a continuity guard. One bounded recovery attempt on 2026-10-07 used the CUA surface inventory followed by the known readiness URL with the explicit `iab` browser. The inventory again had no in-app browser, and the known URL lookup returned `Browser is not available: iab`. Personal Chrome was not controlled.

The final continuity-guard changes are therefore also **unverified in the browser**. Earlier desktop observations and the screenshot are preserved as evidence of the earlier candidate only. Mobile, console, failed-import retention, download/reimport, clear, evidence/correction detail and final hot reload checks remain pending. No verification suite was started or stopped during this recovery attempt.
