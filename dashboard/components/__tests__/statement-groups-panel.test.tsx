import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import path from "node:path";
import { LoadedRunProvider, RunSwitch, useLoadedRun } from "@/components/loaded-run";
import { loadRunDir, loadTieOut } from "@/lib/run-dir";
import type { LoadedRun } from "@/lib/upload";
import { StatementGroupsPanel } from "@/components/statement-groups-panel";

it("distinguishes missing, empty, unknown, excluded and zero grouping", () => {
  const view = render(<StatementGroupsPanel />);
  expect(screen.getByText(/Grouping is unavailable/)).toBeInTheDocument();
  view.rerender(<StatementGroupsPanel groups={[]} />);
  expect(screen.getByText(/No statement rows are available for grouping/)).toBeInTheDocument();
  view.rerender(<StatementGroupsPanel groups={[{ carrier: null, statement_period: null,
    valid_line_count: 0, excluded_line_count: 1, total_paid: null }, { carrier: "Carrier A", statement_period: "2026-09",
    valid_line_count: 2, excluded_line_count: 0, total_paid: "0.00" }]} />);
  expect(screen.getByText("Carrier unavailable")).toBeInTheDocument();
  expect(screen.getByText("Statement period unavailable")).toBeInTheDocument();
  expect(screen.getByText(/No valid amounts/)).toBeInTheDocument();
  expect(screen.getByText("$0.00")).toBeInTheDocument();
});
it("pages groups and resets pagination on same-ID replacement", () => {
  const groups = Array.from({ length: 26 }, (_, i) => ({ carrier: `Carrier ${i}`, statement_period: "2026-09",
    valid_line_count: 1, excluded_line_count: 0, total_paid: "-1.00" }));
  const view = render(<StatementGroupsPanel groups={groups} />);
  expect(screen.queryByText("Carrier label: Carrier 25")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Next group page" }));
  expect(screen.getByText("Carrier label: Carrier 25")).toBeInTheDocument();
  view.rerender(<StatementGroupsPanel groups={[...groups]} />);
  expect(screen.getByText("Carrier label: Carrier 0")).toBeInTheDocument();
});

it("replaces attached groups with unavailable evidence through loaded run state", async () => {
  const dir = path.resolve(import.meta.dirname, "../../../fixtures/sample-run-failed");
  const loaded: LoadedRun = { label: "sample-run-failed", run: await loadRunDir(dir), tieOut: await loadTieOut(dir),
    statementGroups: [{ carrier: "Unknown carrier", statement_period: null, valid_line_count: 1, excluded_line_count: 0, total_paid: "1.00" }] };
  function Controls() {
    const { setLoaded } = useLoadedRun();
    return <><button onClick={() => setLoaded(loaded)}>Attach groups</button>
      <button onClick={() => setLoaded({ ...loaded, statementGroups: undefined })}>Replace groups</button>
      <button onClick={() => setLoaded(null)}>Clear groups</button></>;
  }
  render(<LoadedRunProvider><Controls /><RunSwitch page="tie-out"><p>Demo tie-out</p></RunSwitch></LoadedRunProvider>);
  fireEvent.click(screen.getByText("Attach groups"));
  expect(screen.getByText("Carrier label: Unknown carrier")).toBeInTheDocument();
  expect(screen.getByText("Not checked. The run stopped before the tie-out.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Replace groups"));
  expect(screen.queryByText("Carrier label: Unknown carrier")).toBeNull();
  expect(screen.getByText(/Grouping is unavailable/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Clear groups"));
  expect(screen.getByText("Demo tie-out")).toBeInTheDocument();
});
