import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(import.meta.dirname, "../../app/globals.css"), "utf8");

// Source acceptance only. jsdom cannot prove measured viewport geometry or touch behavior.
function blockAt(marker: string): string {
  const start = css.indexOf(marker);
  if (start < 0) throw new Error(`Missing presentation contract: ${marker}`);
  const opening = css.indexOf("{", start);
  let depth = 1;
  let end = opening + 1;
  for (; depth > 0 && end < css.length; end += 1) {
    if (css[end] === "{") depth += 1;
    if (css[end] === "}") depth -= 1;
  }
  return css.slice(opening + 1, end - 1);
}

describe("Responsive presentation source contracts", () => {
  it("keeps the desktop five-cell quality strip and the narrow-screen single-column baseline", () => {
    expect(blockAt(".metric-strip {")).toContain("grid-template-columns: 1fr");
    expect(blockAt("@media (min-width: 1024px)")).toContain("grid-template-columns: repeat(5, minmax(0, 1fr))");
  });

  it("defines phone touch targets and full-width filters at both 375 and 390 widths", () => {
    const phone = blockAt("@media (max-width: 640px)");
    for (const width of [375, 390]) expect(width).toBeLessThanOrEqual(640);
    expect(phone).toContain(".sidebar-link, .theme-toggle { min-height: 44px; }");
    expect(phone).toContain(".app-main :is(button, select, summary) { min-height: 44px; }");
    expect(phone).toContain(".filter-bar > label { flex: 1 1 100%; min-width: 0; }");
    expect(phone).toContain(".filter-bar select { width: 100%; max-width: 100%; }");
  });

  it("contains wide tables in their own bounded scrollers without hiding evidence", () => {
    const wrapper = blockAt(".evidence-table-wrap {");
    expect(wrapper).toContain("max-width: 100%");
    expect(wrapper).toContain("min-width: 0");
    expect(wrapper).toContain("overflow: auto");
    expect(wrapper).not.toContain("overflow: hidden");
  });

  it("retains readable trust text, long-reference wrapping and reduced-motion treatment", () => {
    expect(blockAt(".synthetic-label {")).toContain("font-size: 12px");
    expect(blockAt(".synthetic-label {")).toContain("line-height: 1.5");
    expect(css).toContain(".source-facts dd, .page-description, .decision-detail, .metric-context { overflow-wrap: anywhere; }");
    expect(blockAt("@media (prefers-reduced-motion: reduce)")).toContain("transition-duration: 0s");
  });
});
