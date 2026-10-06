import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { StatementTotalsPanel } from "@/components/statement-totals-panel";
import type { StatementTotals } from "@/lib/statement-totals";

const lin = { source_file: "statement.csv", sheet: null, row_number: 2, raw_hash: "a".repeat(64), run_id: "run", mapping_version: "unmapped" };
const line = { source: "statement_harborline", lineage: lin, amount: "-12.50", reason: "valid" } as const;
const available: StatementTotals = { schema_version: 1, run_id: "run", status: "AVAILABLE", reason: null,
  valid_line_count: 1, excluded_line_count: 0, total_paid: "-12.50", lines: [line] };

it("separates unavailable, blocked, all excluded, and signed available evidence", () => {
  const view = render(<StatementTotalsPanel />);
  const panel = screen.getByRole("region", { name: "Statement totals" });
  expect(within(panel).getByText(/No statement_totals.json artifact/)).toBeInTheDocument();
  view.rerender(<StatementTotalsPanel totals={{ ...available, status: "BLOCKED", reason: "raw_gate_blocked", lines: [], valid_line_count: 0, total_paid: null }} />);
  expect(within(panel).getByText(/Raw safety or completeness gate blocked/)).toBeInTheDocument();
  view.rerender(<StatementTotalsPanel totals={{ ...available, status: "UNAVAILABLE", reason: "no_statements", lines: [], valid_line_count: 0, total_paid: null }} />);
  expect(within(panel).getByText(/No commission statements were received/)).toBeInTheDocument();
  view.rerender(<StatementTotalsPanel totals={{ ...available, status: "PARTIAL", reason: "excluded_rows", lines: [{ ...line, amount: null, reason: "amount_malformed" }], valid_line_count: 0, excluded_line_count: 1, total_paid: null }} />);
  expect(within(panel).getByText(/No valid statement amounts/)).toBeInTheDocument();
  expect(within(panel).queryByText("$0.00")).toBeNull();
  view.rerender(<StatementTotalsPanel totals={available} />);
  expect(within(panel).getByText("-$12.50")).toBeInTheDocument();
  fireEvent.click(within(panel).getByText("Full source provenance"));
  expect(within(panel).getByText(lin.raw_hash)).toBeInTheDocument();
});

it("pages 26 rows and resets on same-ID replacement", () => {
  const rows = Array.from({ length: 26 }, (_, i) => ({ ...line, lineage: { ...lin, row_number: i + 2 }, amount: "1.00" }));
  const totals = { ...available, valid_line_count: 26, total_paid: "26.00", lines: rows };
  const view = render(<StatementTotalsPanel totals={totals} />);
  const panel = screen.getByRole("region", { name: "Statement totals" });
  expect(within(panel).queryByText(/statement\.csv, row 27/)).toBeNull();
  fireEvent.click(within(panel).getByRole("button", { name: "Next statement page" }));
  expect(within(panel).getByText(/statement\.csv, row 27/)).toBeInTheDocument();
  view.rerender(<StatementTotalsPanel totals={{ ...totals, lines: rows }} />);
  expect(within(panel).getByText(/statement\.csv, row 2$/)).toBeInTheDocument();
});
