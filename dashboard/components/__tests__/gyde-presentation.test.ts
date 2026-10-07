import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(import.meta.dirname, "../../app/globals.css"), "utf8");
const luminance = (hex: string) => hex.slice(1).match(/../g)!
  .map((part) => parseInt(part, 16) / 255)
  .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  .reduce((total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index], 0);
function contrast(a: string, b: string) {
  const levels = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (levels[0] + 0.05) / (levels[1] + 0.05);
}
function theme(selector: string) {
  const block = css.slice(css.indexOf(selector)).split("}")[0];
  const values = Object.fromEntries([...block.matchAll(/--([\w-]+): (#[\da-fA-F]{6});/g)].map((match) => [match[1], match[2]]));
  return (key: string) => { if (!values[key]) throw new Error(`Missing ${selector} ${key}`); return values[key]; };
}

// Contrast is checked from the actual configured values; geometry still needs a browser.
describe("Shared visual accessibility", () => {
  for (const selector of [":root {", ".dark {"]) {
    it(`${selector} keeps text, status icons, controls and focus readable`, () => {
      const value = theme(selector);
      for (const surface of ["background", "card"]) {
        for (const ink of ["foreground", "muted-foreground", "status-error", "status-warning", "status-pass"]) {
          expect(contrast(value(ink), value(surface))).toBeGreaterThanOrEqual(4.5);
        }
        expect(contrast(value("border"), value(surface))).toBeGreaterThanOrEqual(3);
        expect(contrast(value("ring"), value(surface))).toBeGreaterThanOrEqual(3);
      }
      expect(contrast(value("primary-foreground"), value("brand-strong"))).toBeGreaterThanOrEqual(4.5);
    });
  }
  it("separates focus from the selected action and avoids opacity for disabled controls", () => {
    expect(css).toContain(":focus-visible { outline: 2px solid var(--ring); outline-offset: 3px; }");
    expect(css).toContain("opacity: 1; background: var(--card); color: var(--muted-foreground); border-color: var(--border)");
  });
});
