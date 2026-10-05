import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FinanceReviewPanel } from "@/components/finance-review-panel";
import { parseFinanceReview } from "@/lib/finance-review";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);

function makeReview(overrides: Record<string, unknown> = {}) {
  const artifact = {
    artifact_type: "neutral_finance_review",
    schema_version: 1,
    agency_id: "agency-synthetic",
    carrier: "Synthetic Carrier",
    period: "2026-09",
    statement_id: "statement-sample",
    revision_id: "revision-4",
    content_sha256: HASH_A,
    mapping_id: "mapping-42",
    mapping_version: "v3",
    mapping_approved: true,
    approved_by: "Synthetic Reviewer",
    approved_at: "2026-10-05T12:00:00Z",
    mapping_snapshot: {
      mapping_id: "mapping-42",
      carrier: "Synthetic Carrier",
      version: "v3",
      approved_by: "Synthetic Reviewer",
      approved_at: "2026-10-05T12:00:00Z",
      categories: { Renewal: "renewal" },
      transaction_kinds: { Payment: "payment" },
      accounts: { renewal: "2100" },
    },
    mapping_sha256: HASH_B,
    rows: [
      {
        row_id: "row-1",
        amount: "-0.01",
        raw_amount: "-0.01",
        raw_category_label: "Mystery Fee",
        raw_transaction_label: "Payment",
        lineage: {
          source_file: "synthetic-statement.csv",
          sheet: null,
          row_number: 7,
          raw_hash: HASH_C,
          run_id: "run-synthetic",
          mapping_version: "v2",
        },
        category: "unclassified",
        transaction_kind: "payment",
        classification_method: "unresolved",
        unresolved_reasons: ["unknown_category_label", "missing_account_mapping"],
        account_code: null,
        authoritative_policy_id: null,
      },
    ],
    category_totals: {
      new_business: "0.00",
      renewal: "0.00",
      override: "0.00",
      bonus: "0.00",
      marketing: "0.00",
      unclassified: "-0.01",
    },
    statement_total: "-0.01",
    control_total: "0.01",
    total_check: "FAIL",
    ...overrides,
  };
  return parseFinanceReview(artifact);
}

function renderPanel() {
  render(<FinanceReviewPanel statements={[makeReview()]} />);
}

function makePaginatedReview() {
  const review = makeReview();
  const rows = Array.from({ length: 26 }, (_, index) => ({
    ...review.rows[0],
    row_id: `row-${index + 1}`,
    lineage: { ...review.rows[0].lineage, row_number: index + 1 },
  }));
  return parseFinanceReview({
    ...review,
    rows,
    category_totals: { ...review.category_totals, unclassified: "-0.26" },
    statement_total: "-0.26",
  });
}

describe("FinanceReviewPanel", () => {
  it("keeps mapping approval separate from an uncertain statement control total", () => {
    renderPanel();
    expect(screen.getByText("Approved by Synthetic Reviewer at 2026-10-05T12:00:00Z")).toBeInTheDocument();
    expect(screen.getByText("Totals differ")).toBeInTheDocument();
    expect(screen.getByText("This check does not approve the package.")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Statement total" })).getByText("-0.01")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Source control total" })).getByText("0.01")).toBeInTheDocument();
  });

  it("shows an unknown source category and its unresolved reason", () => {
    renderPanel();
    const sourceRows = within(screen.getByRole("region", { name: "Source rows for statement-sample" }));
    const row = sourceRows.getByRole("row", { name: /row-1/ });
    expect(row).toHaveTextContent("Mystery Fee");
    expect(row).toHaveTextContent("unclassified");
    expect(row).toHaveTextContent("unknown category label");
  });

  it("preserves the sign and cents of negative amounts in totals and source rows", () => {
    renderPanel();
    expect(within(screen.getByRole("group", { name: "Statement total" })).getByText("-0.01")).toBeInTheDocument();
    const categoryTotals = within(screen.getByRole("region", { name: "Category totals for statement-sample" }));
    expect(categoryTotals.getByRole("row", { name: /unclassified/ })).toHaveTextContent("-0.01");
    const sourceRows = within(screen.getByRole("region", { name: "Source rows for statement-sample" }));
    expect(sourceRows.getByRole("row", { name: /row-1/ })).toHaveTextContent("-0.01");
  });

  it("shows statement mapping and source-row mapping versions as separate evidence", () => {
    renderPanel();
    expect(screen.getByText("mapping-42 · Version v3")).toBeInTheDocument();
    const sourceRows = screen.getByRole("region", { name: "Source rows for statement-sample" });
    fireEvent.click(within(sourceRows).getByText("synthetic-statement.csv, row 7"));
    expect(within(sourceRows).getByText("Source mapping version").parentElement).toHaveTextContent("v2");
  });

  it("pages to the final source row while keeping full statement totals unchanged", () => {
    const review = makePaginatedReview();
    render(<FinanceReviewPanel statements={[review]} />);
    const sourceRows = () => within(screen.getByRole("region", { name: "Source rows for statement-sample" }));
    const navigation = () => screen.getByRole("navigation", { name: "Source row navigation for statement-sample" });

    expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 2");
    expect(screen.getByRole("status")).toHaveTextContent("Rows 1-25 of 26");
    expect(sourceRows().getByRole("row", { name: /row-25/ })).toBeInTheDocument();
    expect(sourceRows().queryByRole("row", { name: /row-26/ })).not.toBeInTheDocument();

    fireEvent.click(within(navigation()).getByRole("button", { name: "Next rows" }));
    expect(screen.getByRole("status")).toHaveTextContent("Page 2 of 2");
    expect(screen.getByRole("status")).toHaveTextContent("Rows 26-26 of 26");
    expect(sourceRows().getByRole("row", { name: /row-26/ })).toBeInTheDocument();
    expect(sourceRows().queryByRole("row", { name: /row-25/ })).not.toBeInTheDocument();

    expect(within(screen.getByRole("group", { name: "Statement total" })).getByText("-0.26")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Category totals for statement-sample" }))
      .getByRole("row", { name: /unclassified/ })).toHaveTextContent("-0.26");
  });

  it("resets the source page when the statement revision changes", () => {
    const review = makePaginatedReview();
    const { rerender } = render(<FinanceReviewPanel statements={[review]} />);
    const sourceRows = () => within(screen.getByRole("region", { name: "Source rows for statement-sample" }));
    fireEvent.click(within(screen.getByRole("navigation", { name: "Source row navigation for statement-sample" }))
      .getByRole("button", { name: "Next rows" }));
    expect(screen.getByRole("status")).toHaveTextContent("Page 2 of 2");

    const nextRevision = parseFinanceReview({
      ...review,
      revision_id: "revision-5",
      content_sha256: "d".repeat(64),
    });
    rerender(<FinanceReviewPanel statements={[nextRevision]} />);

    expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 2");
    expect(sourceRows().getByRole("row", { name: /^row-1\b/ })).toBeInTheDocument();
    expect(sourceRows().queryByRole("row", { name: /row-26/ })).not.toBeInTheDocument();
  });
});
