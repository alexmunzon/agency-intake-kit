import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunFinance } from "@/components/run-finance";
import { useLoadedRun } from "@/components/loaded-run";
import { parseFinanceReview } from "@/lib/finance-review";
import type { LoadedRun } from "@/lib/upload";

vi.mock("@/components/loaded-run", () => ({ useLoadedRun: vi.fn() }));
const example = parseFinanceReview(readFileSync(path.join(process.cwd(), "public/demo-finance.json"), "utf8"));

describe("finance scope when importing runs", () => {
  it("labels the example separately and removes it for an older imported run", () => {
    vi.mocked(useLoadedRun).mockReturnValue({ loaded: null, setLoaded: vi.fn() });
    const view = render(<RunFinance example={example} />);
    expect(screen.getByText(/Separate synthetic finance example/)).toBeInTheDocument();
    vi.mocked(useLoadedRun).mockReturnValue({ loaded: { label: "older" } as LoadedRun, setLoaded: vi.fn() });
    view.rerender(<RunFinance example={example} />);
    expect(screen.getByText(/no finance.json/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Finance review" })).not.toBeInTheDocument();
  });

  it("shows only the attached statement scope for a run with finance evidence", () => {
    const finance = { ...example, agency_id: "attached-agency" };
    vi.mocked(useLoadedRun).mockReturnValue({ loaded: { label: "attached", finance } as LoadedRun, setLoaded: vi.fn() });
    render(<RunFinance example={example} />);
    expect(screen.getByText(/Agency attached-agency/)).toBeInTheDocument();
    expect(screen.queryByText(/Separate synthetic finance example/)).not.toBeInTheDocument();
  });
});
