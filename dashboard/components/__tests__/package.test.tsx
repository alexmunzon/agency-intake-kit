import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import PackagePage from "@/app/package/page";

describe("Review package", () => {
  it("keeps the five evidence streams separate and exposes their relevant review destinations", () => {
    const doc = new DOMParser().parseFromString(renderToStaticMarkup(<PackagePage />), "text/html");
    expect(doc.querySelector("h1")?.textContent).toBe("Synthetic review package");
    const destinations = [
      ["source-completeness", "Inspect source evidence", "/sources"],
      ["source-completeness", "Review source readiness snapshot", "/readiness"],
      ["excluded-records", "Inspect exceptions", "/exceptions"],
      ["identity-uncertainty", "Inspect identity clusters", "https://bob-resolve-nine.vercel.app/clusters"],
      ["financial-totals", "Inspect financial tie-out", "/tie-out"],
      ["financial-totals", "Inspect receipt ledger snapshot", "/ledger"],
      ["human-review", "Inspect plan changes", "https://plan-diff.vercel.app/changes"],
    ];
    for (const [region, link, href] of destinations) {
      expect(doc.querySelector(`section[aria-labelledby="${region}"] a[href="${href}"]`)?.textContent).toBe(link);
    }
    for (const link of doc.querySelectorAll("a")) {
      const href = link.getAttribute("href")!;
      if (href.startsWith("/")) expect(existsSync(resolve(import.meta.dirname, `../../app${href}/page.tsx`))).toBe(true);
    }
  });

  it("explains independent snapshots, uncertainty, and the limits of browser review labels", () => {
    const doc = new DOMParser().parseFromString(renderToStaticMarkup(<PackagePage />), "text/html");
    const scope = doc.querySelector('section[aria-labelledby="package-scope"]')?.textContent;
    const identity = doc.querySelector('section[aria-labelledby="identity-uncertainty"]')?.textContent;
    const finance = doc.querySelector('section[aria-labelledby="financial-totals"]')?.textContent;
    const review = doc.querySelector('section[aria-labelledby="human-review"]')?.textContent;
    expect(scope).toContain("do not inherit that run, agency, or review state");
    expect(scope).toContain("Hashes establish snapshot consistency, not authenticity");
    expect(scope).toContain("does not automatically correspond to the loaded Intake run");
    expect(scope).toContain("The receipt ledger also opens its own export");
    expect(finance).toContain("local SQLite finance command, with no hosted persistence");
    expect(identity).toContain("Resolved does not mean human-confirmed");
    expect(identity).toContain("local Bob dashboard, open Evidence workflow");
    expect(identity).toContain("accepting evidence does not merge people or resolve identity");
    expect(doc.querySelector('a[href="https://bob-resolve-nine.vercel.app/workflow"]')).toBeNull();
    expect(review).toContain("Browser review labels are not authenticated approval");
    expect(review).toContain("not suitability or purchase recommendations");
  });

  it("keeps real authentication, hosted storage, ERP posting, and real agency data gated", () => {
    const doc = new DOMParser().parseFromString(renderToStaticMarkup(<PackagePage />), "text/html");
    const gates = doc.querySelector('section[aria-labelledby="release-gates"]');
    const labels = [...gates!.querySelectorAll("strong")].map((label) => label.textContent);
    for (const label of ["Real authentication.", "Hosted storage.", "ERP posting.", "Agency data."]) {
      expect(labels).toContain(label);
    }
    expect(gates?.textContent).toContain("separate authorization and implementation");
    expect(doc.querySelector("button")?.textContent).toBe("Load synthetic example");
    expect([...doc.querySelectorAll("button")].find(button => button.textContent === "Clear summary")?.hasAttribute("disabled")).toBe(true);
  });
});
