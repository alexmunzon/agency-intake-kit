import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";

vi.mock("next/font/google", () => ({ Inter: () => ({ variable: "font-sans" }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/exceptions" }));

// jsdom cannot measure layout, so this checks the class that lets the page column shrink.
// Without it, a wide table pushes the page past the window beside the desktop sidebar.
describe("RootLayout", () => {
  it("lets the page column shrink beside the sidebar so wide tables scroll in their own box", () => {
    const html = renderToStaticMarkup(<RootLayout params={Promise.resolve({})}>page</RootLayout>);
    const main = new DOMParser().parseFromString(html, "text/html").querySelector("main");
    expect(main?.className.split(" ")).toContain("min-w-0");
  });
});
