import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

// The dashboard has one palette: light. No toggle, no system-setting switch, no saved preference.
const ROOT = path.resolve(import.meta.dirname, "../..");
const read = (file: string) => readFileSync(path.join(ROOT, file), "utf8");
const css = read("app/globals.css");
const layoutSource = read("app/layout.tsx");

function renderLayout() {
  const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
  return { html, doc: new DOMParser().parseFromString(html, "text/html") };
}

function sourceFiles(dir: string): string[] {
  return readdirSync(path.join(ROOT, dir)).flatMap((name) => {
    const rel = path.join(dir, name);
    if (name === "__tests__" || name === "vendor") return [];
    if (statSync(path.join(ROOT, rel)).isDirectory()) return sourceFiles(rel);
    return /\.(tsx?|css)$/.test(name) ? [rel] : [];
  });
}

/** The declarations inside the first `marker { ... }` block. */
function blockAt(marker: string): string {
  const start = css.indexOf(marker);
  if (start < 0) throw new Error(`Missing block: ${marker}`);
  const opening = css.indexOf("{", start);
  return css.slice(opening + 1, css.indexOf("}", opening));
}

afterEach(() => localStorage.clear());

describe("Light-only dashboard", () => {
  it("renders no dark mode control anywhere in the shell", () => {
    const { doc } = renderLayout();
    const named = [...doc.querySelectorAll("button, a, [role], [aria-label]")].map(
      (el) => `${el.getAttribute("aria-label") ?? ""} ${el.textContent ?? ""}`,
    );
    expect(named.filter((name) => /dark mode/i.test(name))).toEqual([]);
    expect(doc.body.textContent).not.toMatch(/dark mode/i);
    expect(doc.querySelector(".theme-toggle")).toBeNull();
    expect(doc.querySelectorAll("button[aria-pressed]")).toHaveLength(0);
    expect(existsSync(path.join(ROOT, "components/theme-toggle.tsx"))).toBe(false);
  });

  it("never marks the page dark, even with a stale saved dark preference", () => {
    localStorage.setItem("theme", "dark");
    const { html, doc } = renderLayout();
    expect(doc.documentElement.classList.contains("dark")).toBe(false);
    expect(html).not.toMatch(/class="[^"]*\bdark\b/);
    expect(html).not.toContain("data-theme");
    expect(doc.querySelectorAll("head script")).toHaveLength(0);
  });

  it("has no pre-paint theme script or preference lookups in the layout source", () => {
    for (const banned of ["prefers-color-scheme", "localStorage", "matchMedia", "THEME_SCRIPT", "classList", "data-theme", "ThemeToggle"]) {
      expect(layoutSource).not.toContain(banned);
    }
  });

  it("keeps only the light tokens in globals.css and tells native controls to stay light", () => {
    expect(css).not.toMatch(/\.dark\b/);
    expect(css).not.toMatch(/prefers-color-scheme/);
    expect(css).not.toMatch(/@custom-variant\s+dark/);
    expect(css).not.toMatch(/color-scheme:\s*dark/);
    expect(css).not.toContain(".theme-toggle");
    const root = blockAt(":root {");
    expect(root).toContain("color-scheme: light;");
    for (const token of [
      "--background: #F6F5F2;",
      "--card: #FFFFFF;",
      "--foreground: #272727;",
      "--primary: var(--brand-strong);",
      "--brand-strong: #8F202B;",
      "--muted-foreground: #646464;",
      "--border: #858585;",
      "--status-error: #B4233B;",
      "--status-warning: #805600;",
      "--status-pass: #246442;",
      "--sidebar: #FFFFFF;",
      "--sidebar-accent: #8F202B;",
    ]) {
      expect(root).toContain(token);
    }
  });

  it("uses no dark: Tailwind classes in any app or component source", () => {
    const files = [...sourceFiles("app"), ...sourceFiles("components"), ...sourceFiles("lib")];
    expect(files.length).toBeGreaterThan(10);
    const offenders = files.filter((file) => /(^|[\s"'`])dark:/.test(read(file)));
    expect(offenders).toEqual([]);
  });
});
