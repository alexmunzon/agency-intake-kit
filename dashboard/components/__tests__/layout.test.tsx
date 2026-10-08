import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";

vi.mock("next/navigation", () => ({ usePathname: () => "/exceptions" }));

// jsdom cannot measure layout, so this checks the class that lets the page column shrink.
// Without it, a wide table pushes the page past the window beside the desktop sidebar.
describe("RootLayout", () => {
  it("gives keyboard users a skip link to the focusable main content without changing navigation", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelector('a[href="#main-content"]')?.textContent).toBe("Skip to content");
    expect(doc.querySelector("main")?.id).toBe("main-content");
    expect(doc.querySelector("main")?.getAttribute("tabindex")).toBe("-1");
    expect(doc.querySelectorAll('nav[aria-label="Main"] ul a')).toHaveLength(9);
    expect(doc.querySelector('a[href="/package"]')?.textContent).toBe("Review package");
    expect(doc.querySelector('a[href="/readiness"]')?.textContent).toBe("Source readiness");
    expect(doc.querySelector('a[href="/ledger"]')?.textContent).toBe("Revenue breakdown");
  });

  it("shows one short trust notice and keeps the theme footer after navigation and demo links", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const doc = new DOMParser().parseFromString(html, "text/html");
    const notice = doc.querySelector('[aria-label="Review scope"]');
    expect(notice?.textContent).toBe("Synthetic demo · human review required");
    expect(doc.querySelectorAll('[aria-label="Review scope"]')).toHaveLength(1);
    const nav = doc.querySelector('nav[aria-label="Main"]')!;
    expect(nav.lastElementChild?.classList.contains("sidebar-footer")).toBe(true);
    expect(nav.lastElementChild?.querySelector("button")?.textContent).toBe("Dark mode");
    expect(nav.textContent).not.toContain("human review required");
  });

  it("lets the page column shrink beside the sidebar so wide tables scroll in their own box", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const main = new DOMParser().parseFromString(html, "text/html").querySelector("main");
    expect(main?.className.split(" ")).toContain("min-w-0");
  });

  it("links the three separate demos in walkthrough order without claiming a connected pipeline", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const doc = new DOMParser().parseFromString(html, "text/html");
    const series = doc.querySelector('[aria-label="Agency Data Trust Series"]');
    expect(series?.textContent).toContain("Separate demos");
    expect(series?.querySelector('[aria-current="page"]')?.textContent).toBe("1. Agency Intake Kit");
    expect(series?.querySelector('a[href="https://bob-resolve-nine.vercel.app"]')?.textContent).toBe("2. Bob Resolve");
    expect(series?.querySelector('a[href="https://plan-diff.vercel.app"]')?.textContent).toBe("3. Plan Diff");
  });
});
