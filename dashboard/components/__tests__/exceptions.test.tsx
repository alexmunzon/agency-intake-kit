import path from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExceptionsView } from "@/components/exceptions-view";
import { Sources } from "@/components/sources";
import { loadRunDir } from "@/lib/run-loader";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const load = (name: string) => loadRunDir(path.join(FIXTURES, name));

function bodyRows() {
  return within(screen.getByRole("table")).getAllByRole("row").slice(1);
}

describe("Exceptions page", () => {
  it("shows the CMP-001 blocker in the first row of the failed sample", async () => {
    render(<ExceptionsView records={(await load("sample-run-failed")).exceptions} />);
    expect(within(bodyRows()[0]).getByText("CMP-001")).toBeInTheDocument();
    expect(within(bodyRows()[0]).getByText("Blocker")).toBeInTheDocument();
  });

  it("filters the table by severity, rule, and source", async () => {
    render(<ExceptionsView records={(await load("sample-run")).exceptions} />);
    expect(bodyRows()).toHaveLength(13);
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "ERROR" } });
    expect(bodyRows()).toHaveLength(4);
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "statement_harborline" } });
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 13 exceptions");
    fireEvent.change(screen.getByLabelText("Rule"), { target: { value: "RTS-001" } });
    expect(screen.getByText(/No exceptions match/)).toBeInTheDocument();
  });

  it("opens a drawer with lineage, fix, and Jev scores, and closes it on Escape", async () => {
    render(<ExceptionsView records={(await load("sample-run")).exceptions} />);
    fireEvent.click(bodyRows().find((row) => within(row).queryByText("DOB-002"))!);
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByText("crm_export.csv")).toBeInTheDocument();
    expect(drawer.getByText("118")).toBeInTheDocument();
    expect(drawer.getByText("d382fd48a540d03975cef90c276c90ec516146c8f7603c188139b19d46aaa718")).toBeInTheDocument();
    expect(drawer.getByText("18**-**-**")).toBeInTheDocument();
    expect(drawer.getByText("The date of birth gives an age of 168")).toBeInTheDocument();
    expect(drawer.getByText("Check for a century error")).toBeInTheDocument();
    expect(drawer.getByText("93%")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains a whole-file exception in the drawer on the passed sample", async () => {
    render(<ExceptionsView records={(await load("sample-run-passed")).exceptions} />);
    fireEvent.keyDown(bodyRows()[0], { key: "Enter" });
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByText("This is about the whole file, not one row.")).toBeInTheDocument();
    expect(drawer.getByText("Not reviewed by Jev.")).toBeInTheDocument();
  });

  it("shows a notes value as [redacted]", async () => {
    const [record] = (await load("sample-run")).exceptions.filter((r) => r.rule_id === "DOB-002");
    render(<ExceptionsView records={[{ ...record, field: "notes", value_minimized: "Ca*** ***" }]} />);
    fireEvent.click(bodyRows()[0]);
    expect(within(screen.getByRole("dialog")).getByText("[redacted]")).toBeInTheDocument();
  });
});

describe("Sources page", () => {
  it("shows expected 2,600 versus received 2,574 on the failed sample", async () => {
    render(<Sources run={await load("sample-run-failed")} />);
    const crm = within(screen.getByRole("region", { name: "crm_export.csv" }));
    expect(crm.getByText("2,600")).toBeInTheDocument();
    expect(crm.getByText("2,574")).toBeInTheDocument();
    expect(crm.getByText("Blocked the run")).toBeInTheDocument();
    expect(screen.getByText("4 of 5 files read cleanly.")).toBeInTheDocument();
  });

  it("reads all five files cleanly on the passed sample", async () => {
    render(<Sources run={await load("sample-run-passed")} />);
    expect(screen.getByText("5 of 5 files read cleanly.")).toBeInTheDocument();
  });
});
