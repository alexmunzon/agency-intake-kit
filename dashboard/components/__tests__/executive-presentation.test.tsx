import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExceptionsView } from "@/components/exceptions-view";
import { Overview } from "@/components/overview";
import { PageHeader, TieOutView } from "@/components/tie-out";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";

const SAMPLE = path.resolve(import.meta.dirname, "../../../fixtures/sample-run");

describe("Executive presentation", () => {
  it("keeps the decision, quality metrics and check context in distinct named regions", async () => {
    const run = await loadRunDir(SAMPLE);
    render(<Overview run={run} tieOut={await loadTieOut(SAMPLE)} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("What needs review before handoff?");
    const decision = within(screen.getByRole("region", { name: "Run status" }));
    expect(decision.getByText("Review required before handoff.")).toBeInTheDocument();
    expect(decision.getByRole("link", { name: "See the exceptions" })).toHaveAttribute("href", "/exceptions");
    const quality = within(screen.getByRole("region", { name: "Load quality" }));
    expect(quality.getAllByRole("group")).toHaveLength(4);
    expect(quality.queryByRole("group", { name: "Info" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Info" })).toHaveTextContent("Informational notes3Notes only");
    expect(screen.getByRole("group", { name: "Info" })).not.toHaveClass("metric-tile");
    expect(quality.getByRole("group", { name: "Clean rows" })).toHaveTextContent("7,761");
    const checks = within(screen.getByRole("region", { name: "Financial and operational checks" }));
    expect(checks.getByRole("group", { name: "Check variance sum" })).toHaveTextContent("This is not a missing-revenue total.");
    expect(checks.queryByRole("group", { name: "Run time" })).not.toBeInTheDocument();
    expect(screen.getByText("Technical run details").closest("details")).not.toHaveAttribute("open");
    expect(decision.getByText(/not agency go-live approval/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Financial and operational checks" }).querySelector(".overview-check-grid")).toHaveClass("sm:grid-cols-2");
  });

  it("makes bounded exception and financial evidence scroll regions keyboard focusable", async () => {
    const run = await loadRunDir(SAMPLE);
    const { unmount } = render(<ExceptionsView records={run.exceptions} />);
    expect(screen.getByRole("region", { name: "Exceptions, blockers first table" })).toHaveAttribute("tabindex", "0");
    unmount();
    render(<TieOutView run={run} tieOut={await loadTieOut(SAMPLE)} />);
    for (const name of ["Differences to review table", "Totals by carrier table", "Totals by agent table"]) {
      expect(screen.getByRole("region", { name })).toHaveAttribute("tabindex", "0");
    }
  });

  it("retains run identity without repeating the shared synthetic-data notice", async () => {
    const run = await loadRunDir(SAMPLE);
    render(<PageHeader run={run} question="Does the money agree?">Review the evidence.</PageHeader>);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByText("Synthetic data only.")).not.toBeInTheDocument();
    expect(screen.getByText(run.manifest.run_id)).toBeInTheDocument();
    expect(screen.getByText("Review the evidence.")).toBeInTheDocument();
  });
});
