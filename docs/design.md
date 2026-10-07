# Dashboard design

The dashboard is for an agency owner who has never seen a data pipeline and for a hiring manager scanning the README. Both need the answer before the detail, so every page asks one question at the top and answers it in the first screen. The full brief is section 9 of `BUILD-GUIDE-agency-intake-kit.md`; this file records what is actually in use.

## Pages and the one question each answers

| Page | Question on the page | Screenshot |
|---|---|---|
| Overview | Can this agency go live? | `screenshots/overview-1440.png`, `overview-375.png`, `overview-dark.png` |
| Sources | What did we receive, and did it read cleanly? | `screenshots/sources-1440.png` |
| Exceptions | What needs fixing, in what order, and how? | `screenshots/exceptions-1440.png` |
| Tie-out | Does the money agree? | `screenshots/tie-out-1440.png` |
| Agents | Is every writing agent allowed to sell what they sold? | `screenshots/agents-1440.png` |
| Runs | Load your own run | none |

**Runs.** Pick a run folder's files (or drop the folder) and every page shows that run, with a banner naming it and a button back to the demo run. The files are read in the browser tab only: nothing is uploaded, nothing is stored, and a reload clears them. Each problem names its file, for example "rts_coverage.json: missing". To compare two runs, use `uv run intake diff <run_a> <run_b>` in the engine.

**Dark mode.** The Dark mode button (sidebar on desktop, top bar on phones) switches it and remembers the choice in the browser. Without a saved choice the page follows the system setting. A small script in the page head applies it before the first paint, so a dark page never flashes white.

**Accessibility checks.** `cd dashboard && npx playwright test e2e/a11y.spec.ts` runs axe (WCAG 2.1 A and AA) on every page in light and dark, plus the open lineage drawer and a loaded run, and fails on any serious or critical finding. It also checks every page at 375 wide for sideways scroll in both schemes. Like the screenshots, it needs the Chromium download, so it is not part of `npm run verify`.

## Design system

**Color tokens.** Colors are CSS variables in `dashboard/app/globals.css` (`:root` for light, `.dark` for dark), shared with Bob Resolve and Plan Diff so the series looks like one product. Components use the tokens through Tailwind and shadcn names (`bg-background`, `text-muted-foreground`, `bg-primary` and so on), never raw palette classes.

| Role | Light | Dark |
|---|---|---|
| Page background | `#F7F3EB` warm offwhite | `#30251F` |
| Cards and panels | `#FFFDF8` ivory | `#403128` raised brown |
| Sidebar | `#30251F` with ivory text and `#D3C0AD` secondary text | same |
| Text | `#30251F` deep brown | `#F7F3EB` |
| Secondary text | `#6B5749` | `#D3C0AD` |
| Borders and inputs | `#9A8370` | `#9A8370` |
| Primary action and active nav item | `#8F3D3D` burgundy with `#F7F3EB` ivory text | same |
| Focus ring | `#30251F` | `#F7F3EB` |

- One accent: the burgundy is the only brand color. Text links use burgundy in light mode and `#E8B7AE` in dark mode. Sidebar focus uses ivory in both themes. Panels are flat (1px borders, no decorative bands or tinted surfaces), and color is saved for meaning.
- Radius: small and square-leaning. The base `--radius` is 6px; most buttons, selects and severity badges use 4px.
- Contrast: body and secondary text meet 4.5:1 and borders and focus rings meet 3:1 in both modes (checked by `components/__tests__/gyde-presentation.test.ts`).

**shadcn.** The project is set up for shadcn (`components.json`, style `base-nova`, built on Base UI, lucide icons), and shadcn's base stylesheet supplies the base layer. It is vendored unchanged at `dashboard/app/vendor/shadcn/tailwind.css` instead of installed as a package, because the package pulled in an unpatched braces advisory; `npx shadcn add` still works on demand. Only the Button primitive is installed so far. The page parts (tiles, banners, severity badges, tables, the lineage drawer) are small local components in `dashboard/components/`, styled with the tokens above.

**Severity colors.** The meaning of each severity is fixed, and color is never the only signal: every severity also has an icon and a word (`components/severity-badge.tsx`). Blocker and Error share one color and are told apart by icon and word.

| Severity | Color token | Light | Dark | Icon | What it means |
|---|---|---|---|---|---|
| Blocker | `--status-error` | `#B4233B` | `#FF9DAE` | octagon | Stops the whole load. The run is FAILED and no load files are written. Only MAP-003, CMP-001, SSN-001. |
| Error | `--status-error` | `#B4233B` | `#FF9DAE` | triangle | The row is kept out of the load files until fixed. The run can still pass with warnings. |
| Warning | `--status-warning` | `#805600` | `#E8C071` | circle alert | The row loads with a flag. Worth a look. |
| Info | secondary text | `#6B5749` | `#D3C0AD` | circle info | A note only. Nothing to fix. |
| Pass | `--status-pass` | `#246442` | `#9CD5B2` | check | The check ran and found nothing. |

**Type.** The system UI font stack (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`) for text, and `ui-monospace` for ids, rule codes and file names. No web fonts are downloaded.

| Use | Size |
|---|---|
| Page question (h1) | 36px, weight 650 |
| The single number in a tile | 30px |
| Readiness answer | 22px |
| Section headings | 14 to 22px (evidence panels 18px) |
| Body text | 14px |
| Evidence table text | 13px |
| Labels, eyebrows, table headers | 10 to 11px uppercase, letter-spaced |

At 540px and below the page question drops to 28px and the readiness answer to 20px.

Every number uses `tabular-nums` so columns line up. Money always shows two decimals and thousands separators.

**Layout.** A 240px left sidebar plus a content column up to 1400px wide. Below 1024px the sidebar becomes a top bar with the navigation in a sideways-scrolling row, tiles stack, and wide tables scroll inside their own box, never the whole page.

## Screenshots

The images in `docs/screenshots/` come from the committed demo run in `dashboard/public/demo-run`, which is frozen (`npm run demo` uses a fixed clock), so they do not change unless the data or the pages change.

To regenerate them (Node 24):

```bash
cd dashboard && npx playwright install chromium   # first time only, downloads the browser
cd .. && npm run shots
```

`npm run shots` builds the site, serves it on port 3000, and writes seven PNGs. Animations are turned off and reduced motion is on, so two runs give identical files. The same run also checks that the Overview readiness answer and every tile fit in the first 1440 by 900 screen and that no page scrolls sideways at 1440 or at 375 wide. It is not part of `npm run verify` because it needs a browser download.
