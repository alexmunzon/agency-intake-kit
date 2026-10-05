import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview } from "@/components/overview";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";
import type { Run } from "@/lib/run-loader";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

async function show(name: string, change?: (run: Run) => void) {
  const dir = path.join(FIXTURES, name);
  const run = await loadRunDir(dir);
  change?.(run);
  render(<Overview run={run} tieOut={await loadTieOut(dir)} />);
}

function tile(label: string) {
  return within(screen.getByRole("group", { name: label }));
}

describe("Overview", () => {
  it("answers yes with fixes for the warnings sample", async () => {
    await show("sample-run");
    expect(screen.getByText("Yes, with fixes to review.")).toBeInTheDocument();
    expect(tile("Blockers").getByText("0")).toBeInTheDocument();
    expect(tile("Errors").getByText("4")).toBeInTheDocument();
    expect(tile("Warnings").getByText("6")).toBeInTheDocument();
    expect(tile("Info").getByText("3")).toBeInTheDocument();
    expect(tile("Clean rows").getByText("7,761")).toBeInTheDocument();
    expect(tile("Clean rows").getByText("of 7,765 rows read")).toBeInTheDocument();
    expect(tile("Tie-out differences").getByText("$85.55")).toBeInTheDocument();
    expect(tile("Tie-out differences").getByText("3 items, all 3 checks ran, plus 1 commission off the rate table or totals ($6.50)")).toBeInTheDocument();
    expect(tile("RTS gaps").getByText("1")).toBeInTheDocument();
    expect(tile("Jev AI review").getByText("38 calls")).toBeInTheDocument();
    expect(tile("Jev AI review").getByText("$0.000901 estimated, replay mode")).toBeInTheDocument();
    expect(tile("Run time").getByText("47 seconds")).toBeInTheDocument();
    expect(tile("Run time").getByText("Run on Oct 1, 2026")).toBeInTheDocument();
    expect(screen.getByText("3 errors, 5 warnings, 1 info")).toBeInTheDocument();
  });

  it("answers no for the failed sample and never shows a missing check as zero", async () => {
    await show("sample-run-failed");
    expect(screen.getByText("No. A blocker stopped the run.")).toBeInTheDocument();
    expect(screen.getByText("crm_export.csv: expected 2,680 rows, received 2,574.")).toBeInTheDocument();
    expect(tile("Blockers").getByText("1")).toBeInTheDocument();
    expect(tile("Errors").getByText("Not checked")).toBeInTheDocument();
    expect(tile("Warnings").getByText("Not checked")).toBeInTheDocument();
    expect(tile("Clean rows").getByText("None")).toBeInTheDocument();
    expect(tile("Tie-out differences").getByText("Not checked")).toBeInTheDocument();
    expect(tile("RTS gaps").getByText("Not checked")).toBeInTheDocument();
    expect(tile("Clean rows").getByText("No load files written")).toBeInTheDocument();
    expect(tile("Jev AI review").getByText("0 calls")).toBeInTheDocument();
  });

  it("answers yes for the passed sample", async () => {
    await show("sample-run-passed");
    expect(screen.getByText("Yes. Every check passed.")).toBeInTheDocument();
    expect(tile("Clean rows").getByText("7,765")).toBeInTheDocument();
    expect(tile("Tie-out differences").getByText("$0.00")).toBeInTheDocument();
    expect(tile("RTS gaps").getByText("0")).toBeInTheDocument();
    expect(tile("Errors").getByText("0")).toBeInTheDocument();
  });

  it("shows warnings found before a blocker stopped the run, with honest context", async () => {
    await show("sample-run-failed", (run) => {
      run.exceptions.push({ ...run.exceptions[1], id: "EX-000003", rule_id: "CMP-002", severity: "WARNING", family: "CMP", source: "statement_crestview" });
      run.scorecard.exceptions_by_severity.warning = 1;
    });
    expect(tile("Warnings").getByText("1")).toBeInTheDocument();
    expect(tile("Warnings").getByText("Found before the run stopped. Row checks did not run.")).toBeInTheDocument();
    expect(tile("Errors").getByText("Not checked")).toBeInTheDocument();
    expect(tile("Info").getByText("Found before the run stopped. Row checks did not run.")).toBeInTheDocument();
  });

  it("says 2 of 3 checks ran for a partial tie-out (#18)", async () => {
    await show("sample-run-partial");
    expect(tile("Tie-out differences").getByText("$85.55")).toBeInTheDocument();
    expect(tile("Tie-out differences").getByText("2 items, 2 of 3 checks ran, plus 1 commission off the rate table or totals ($6.50)")).toBeInTheDocument();
    expect(tile("Warnings").getByText("5")).toBeInTheDocument();
  });
});
