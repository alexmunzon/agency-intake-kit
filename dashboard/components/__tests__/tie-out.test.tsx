import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TieOutView } from "@/components/tie-out";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

async function show(name: string) {
  const dir = path.join(FIXTURES, name);
  render(<TieOutView run={await loadRunDir(dir)} tieOut={await loadTieOut(dir)} />);
}

const leg = (name: string) => within(screen.getByRole("group", { name }));

describe("TieOutView", () => {
  it("shows the three legs and example 4 for the warnings sample", async () => {
    await show("sample-run");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Does the money agree?");
    expect(leg("B. Statement vs book").getByText("2,412")).toBeInTheDocument();
    expect(leg("B. Statement vs book").getByText("$61.05")).toBeInTheDocument();
    const row = within(screen.getByRole("row", { name: /HL-998213/ }));
    expect(row.getByText("TIE-002")).toBeInTheDocument();
    expect(row.getByText("No confirmed policy link")).toBeInTheDocument();
    expect(row.getByText("Harborline 2026-08, line 212")).toBeInTheDocument();
    expect(row.getByText("Harborline paid a commission for a member who is not in the book")).toBeInTheDocument();
    const carriers = within(screen.getByRole("table", { name: "Totals by carrier" }));
    expect(carriers.getByRole("row", { name: /Harborline/ })).toHaveTextContent("$61.05");
    expect(carriers.getByRole("row", { name: /All carriers/ })).toHaveTextContent("$30.05 more paid");
    const agents = within(screen.getByRole("table", { name: "Totals by agent" }));
    expect(agents.getByRole("row", { name: /2210457/ })).toHaveTextContent("$31.00 less paid");
  });

  it("shows Not checked, never zeros, when every leg is NOT_RUN", async () => {
    await show("sample-run-failed");
    expect(screen.getByText("Not checked. The run stopped before the tie-out.")).toBeInTheDocument();
    for (const name of ["A. Book vs statement", "B. Statement vs book", "C. CRM vs statement"]) {
      expect(leg(name).getByText("Not checked")).toBeInTheDocument();
      expect(leg(name).queryByText("0")).toBeNull();
    }
    expect(screen.queryByText("$0.00")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getAllByText(/CMP-001/).length).toBeGreaterThan(0);
  });

  it("answers yes for the passed sample", async () => {
    await show("sample-run-passed");
    expect(screen.getByText("Yes. Every check ran and the money agrees.")).toBeInTheDocument();
    expect(screen.getByText("No differences found.")).toBeInTheDocument();
  });

  it("counts the same differences the table lists, including the rate-table check", async () => {
    await show("sample-run");
    const table = within(screen.getByRole("table", { name: "Differences to review" }));
    const rows = table.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    expect(screen.getByText("Not fully. 4 differences to review.")).toBeInTheDocument();
    expect(
      screen.getByText("$85.55 in differences across 3 of 3 checks, plus 1 commission off the rate table or totals ($6.50)."),
    ).toBeInTheDocument();
  });

  it("says a status disagreement has no amount instead of paid nothing", async () => {
    await show("sample-run");
    const row = within(screen.getByRole("row", { name: /HL-331540/ }));
    expect(row.getByText("Status only, no amount")).toBeInTheDocument();
    expect(row.queryByText(/Paid nothing, expected nothing/)).toBeNull();
    expect(row.queryByText("Even")).toBeNull();
  });

  it("shows Not reported, never zero, for a count a leg left out", async () => {
    const dir = path.join(FIXTURES, "sample-run");
    const tieOut = await loadTieOut(dir);
    tieOut.legs[0] = { ...tieOut.legs[0], matched: null, variance_dollars: null };
    render(<TieOutView run={await loadRunDir(dir)} tieOut={tieOut} />);
    expect(leg("A. Book vs statement").getAllByText("Not reported")).toHaveLength(2);
  });

  it("shows a partial run: two legs with numbers, one leg not checked (#18)", async () => {
    await show("sample-run-partial");
    expect(screen.getByText("Not fully. 3 differences to review.")).toBeInTheDocument();
    expect(
      screen.getByText("$85.55 in differences across 2 of 3 checks, plus 1 commission off the rate table or totals ($6.50)."),
    ).toBeInTheDocument();
    expect(leg("A. Book vs statement").getByText("$24.50")).toBeInTheDocument();
    expect(leg("B. Statement vs book").getByText("$61.05")).toBeInTheDocument();
    const crm = leg("C. CRM vs statement");
    expect(crm.getByText("Not checked")).toBeInTheDocument();
    expect(crm.getByText(/no policy status column/)).toBeInTheDocument();
    expect(crm.queryByText(/\$0\.00|^0$/)).toBeNull();
    expect(screen.queryByRole("row", { name: /HL-331540/ })).toBeNull();
  });

  it("says Partly when the checks that ran agree but one did not run", async () => {
    const dir = path.join(FIXTURES, "sample-run-partial");
    const run = await loadRunDir(dir);
    const tieOut = await loadTieOut(dir);
    for (const summary of run.scorecard.tie_out) {
      if (summary.status === "RAN") Object.assign(summary, { variance_count: 0, variance_dollars: "0.00" });
    }
    tieOut.variances = [];
    render(<TieOutView run={run} tieOut={tieOut} />);
    expect(screen.getByText("Partly. The checks that ran agree.")).toBeInTheDocument();
    expect(screen.getByText("Only 2 of 3 checks ran.")).toBeInTheDocument();
  });
});
