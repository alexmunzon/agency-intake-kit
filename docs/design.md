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

The Runs page (what changed since the last run) arrives in PR 16.

## Design system

**Tailwind v4 tokens.** Colors are Tailwind's built-in palette, used directly in class names (no custom theme colors):

- Neutrals: slate. Page background slate-50 (light) or slate-950 (dark); cards and the nav are white or slate-900.
- Text: slate-900 and slate-600 in light, slate-100 and slate-400 in dark.
- Borders: 1px slate-200 or slate-800. No drop shadows.
- One accent: indigo (600 in light, 400 in dark) for links, the active nav item, and focus rings.
- Radius: `rounded-lg` (8px) on cards, `rounded-md` (6px) on chips.

**shadcn.** The project is set up for shadcn (`components.json`, style `base-nova`, built on Base UI, lucide icons), and `shadcn/tailwind.css` supplies the base layer. Only the Button primitive is installed so far. The page parts (tiles, banners, severity badges, tables, the lineage drawer) are small local components in `dashboard/components/`, styled with the tokens above.

**Severity colors.** The meaning of each color is fixed, and color is never the only signal: every severity also has an icon and a word (`components/severity-badge.tsx`).

| Severity | Color | Icon | What it means |
|---|---|---|---|
| Blocker | rose-600 | octagon | Stops the whole load. The run is FAILED and no load files are written. Only MAP-003, CMP-001, SSN-001. |
| Error | orange-600 | triangle | The row is kept out of the load files until fixed. The run can still pass with warnings. |
| Warning | amber-500 (icon text amber-600) | circle alert | The row loads with a flag. Worth a look. |
| Info | sky-600 | circle info | A note only. Nothing to fix. |
| Pass | emerald-600 | check | The check ran and found nothing. |

In dark mode the icon and text shades move up to the 400 step so they keep enough contrast.

**Type scale.** Inter (via `next/font`) for text, `ui-monospace` for ids, rule codes, and file names.

| Use | Size |
|---|---|
| Page question (h1) | `text-2xl` (24px), semibold |
| The single number in a tile | `text-2xl` (24px), semibold |
| Banner status line | `text-lg` (18px), semibold |
| Body and table text | `text-sm` (14px) |
| Tile context lines, chips, ids | `text-xs` (12px) |

Every number uses `tabular-nums` so columns line up. Money always shows two decimals and thousands separators.

**Layout.** A 240px left nav plus a content column up to 1120px wide with 40px gutters, which fits 1440 exactly. At phone width the nav becomes a top bar that scrolls sideways, tiles stack to one column, and wide tables scroll inside their own box, never the whole page.

## Screenshots

The images in `docs/screenshots/` come from the committed demo run in `dashboard/public/demo-run`, which is frozen (`npm run demo` uses a fixed clock), so they do not change unless the data or the pages change.

To regenerate them (Node 24):

```bash
cd dashboard && npx playwright install chromium   # first time only, downloads the browser
cd .. && npm run shots
```

`npm run shots` builds the site, serves it on port 3000, and writes seven PNGs. Animations are turned off and reduced motion is on, so two runs give identical files. The same run also checks that the Overview fits one 1440 by 900 screen and that no page scrolls sideways at 1440 or at 375 wide. It is not part of `npm run verify` because it needs a browser download.
