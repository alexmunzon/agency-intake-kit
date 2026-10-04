import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NavLink } from "@/components/nav-link";

vi.mock("next/navigation", () => ({ usePathname: () => "/tie-out" }));

describe("NavLink", () => {
  it("marks only the page you are on as current", () => {
    render(<><NavLink href="/" label="Overview" /><NavLink href="/tie-out" label="Tie-out" /></>);
    expect(screen.getByRole("link", { name: "Tie-out" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });
});
