import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import RootLayout from "@/app/layout";
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
describe("Visible demo version", () => {
  it("keeps an accessible V2 badge beside the app title", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const doc = new DOMParser().parseFromString(html, "text/html");
    const badge = doc.querySelector('[data-version-badge]');
    expect(badge?.querySelector('[aria-hidden="true"]')?.textContent).toBe("V2");
    expect(badge?.querySelector(".sr-only")?.textContent).toBe("Version 2");
    expect(badge?.closest(".sidebar-brand")).not.toBeNull();
    expect(doc.querySelectorAll('[data-version-badge]')).toHaveLength(1);
  });
});
