import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(import.meta.dirname, "../../app/globals.css"), "utf8");
const tones = readFileSync(path.resolve(import.meta.dirname, "../severity-badge.tsx"), "utf8");

// Design-token acceptance. Browser contrast and geometry are verified separately.
describe("Warm consulting presentation", () => {
  it("uses the requested palette with a distinct accessible primary action", () => {
    expect(css).toContain("--brand-accent: #ff2727;");
    expect(css).toContain("--brand-strong: #af0505;");
    expect(css).toContain("--background: #f5f5f4;");
    expect(css).toContain("--foreground: #292524;");
    expect(css.match(/--primary: var\(--brand-strong\);/g)).toHaveLength(2);
    expect(css.match(/--primary-foreground: #ffffff;/g)).toHaveLength(2);
  });

  it("gives the configured action and dark-link colors AA text contrast", () => {
    const luminance = (hex: string) => hex.slice(1).match(/../g)!
      .map((part) => parseInt(part, 16) / 255)
      .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
      .reduce((total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index], 0);
    for (const [text, surface] of [["#ffffff", "#af0505"], ["#ffb3aa", "#292524"]]) {
      const levels = [luminance(text), luminance(surface)].sort((a, b) => b - a);
      expect((levels[0] + 0.05) / (levels[1] + 0.05)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps brand decoration separate from fixed severity signals", () => {
    expect(css).toContain(".page-header::before");
    expect(css).toContain("background: var(--brand-accent)");
    for (const tone of ["rose", "orange", "amber", "sky", "emerald"]) {
      expect(tones).toContain(`text-${tone}-600`);
    }
    expect(css).not.toContain(".severity-badge { color: var(--primary)");
  });

  it("retains readable dark links while keeping white-text primary buttons", () => {
    expect(css).toContain(".dark .text-primary");
    expect(css).toContain("color: #ffb3aa");
    expect(css).toContain("color: var(--primary-foreground)");
  });
});
