import path from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentsView } from "@/components/agents";
import { ExceptionsView } from "@/components/exceptions-view";
import { Overview } from "@/components/overview";
import { Sources } from "@/components/sources";
import { TieOutView } from "@/components/tie-out";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";

// The real run that `npm run demo` writes (PR 12), not a hand-written sample.
const DEMO = path.resolve(import.meta.dirname, "../../public/demo-run");

describe("the committed demo run", () => {
  it("loads, checks out, and answers the Overview question", async () => {
    const run = await loadRunDir(DEMO);
    expect(run.manifest.run_id).toBe("demo");
    expect(run.manifest.status).toBe("PASSED_WITH_WARNINGS");
    expect(run.manifest.as_of).toBe("2026-10-01T09:00:00Z");
    expect(run.manifest.budget_tripped).toBe(false);
    expect(run.scorecard.exceptions_by_severity.blocker).toBe(0);
    render(<Overview run={run} tieOut={await loadTieOut(DEMO, run)} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("renders every page from the real files", async () => {
    const run = await loadRunDir(DEMO);
    const tieOut = await loadTieOut(DEMO, run);
    render(<Sources run={run} />);
    render(<ExceptionsView records={run.exceptions} />);
    render(<TieOutView run={run} tieOut={tieOut} />);
    render(<AgentsView run={run} />);
    expect(screen.getAllByText(/HL-998213/).length).toBeGreaterThan(0);
  });
});
