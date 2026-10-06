import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview } from "@/components/overview";
import { TieOutView } from "@/components/tie-out";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";

const FIXTURE = path.resolve(import.meta.dirname, "../../../fixtures/sample-run");
const SUMMARY = "Sum across checks; a line can appear more than once. This is not a missing-revenue total.";

async function sample() {
  return { run: await loadRunDir(FIXTURE), tieOut: await loadTieOut(FIXTURE) };
}

describe("money wording with unresolved attribution", () => {
  it("keeps TIE-001/TIE-002 neutral and labels net unattributed dollars", async () => {
    const { run, tieOut } = await sample();
    render(<TieOutView run={run} tieOut={tieOut} />);
    expect(screen.getByText(SUMMARY)).toBeInTheDocument();
    const differences = within(screen.getByRole("table", { name: "Differences to review" }));
    for (const rule of ["TIE-001", "TIE-002"]) {
      const row = differences.getByRole("row", { name: new RegExp(rule) });
      expect(row).not.toHaveTextContent(/paid nothing|expected nothing|more paid|less paid|even/i);
    }
    const totals = within(screen.getByRole("table", { name: "Totals by carrier" }));
    const headers = totals.getAllByRole("columnheader").map((cell) => cell.textContent);
    const paidIndex = headers.indexOf("Paid");
    const unattributedIndex = headers.indexOf("Unattributed (net)");
    expect(unattributedIndex).toBeGreaterThanOrEqual(0);
    const harborline = totals.getByRole("row", { name: /Harborline/ });
    const cells = within(harborline).getAllByRole("cell");
    expect(cells[paidIndex - 1]).toHaveTextContent("$18,301.05");
    expect(cells[unattributedIndex - 1]).toHaveTextContent("$61.05");
    expect(totals.getByRole("row", { name: /All carriers/ })).toHaveTextContent("$28,145.55");
  });

  it("labels the Overview tile as an overlapping variance sum", async () => {
    const { run, tieOut } = await sample();
    render(<Overview run={run} tieOut={tieOut} />);
    const summary = within(screen.getByRole("group", { name: "Check variance sum" }));
    expect(summary.getByText("$85.55")).toBeInTheDocument();
    expect(summary.getByText(SUMMARY)).toBeInTheDocument();
  });
});
