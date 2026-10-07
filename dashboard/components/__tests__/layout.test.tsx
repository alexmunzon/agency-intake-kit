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
    expect(doc.querySelector('a[href="/ledger"]')?.textContent).toBe("Receipt ledger");
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
    expect(series?.querySelector('[aria-current="page"]')?.textContent).toBe("1. Intake Kit");
    expect(series?.querySelector('a[href="https://bob-resolve-nine.vercel.app"]')?.textContent).toBe("2. Bob Resolve");
    expect(series?.querySelector('a[href="https://plan-diff.vercel.app"]')?.textContent).toBe("3. Plan Diff");
  });
});
