import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LinkEvidencePanel } from "@/components/link-evidence-panel";
import type { LinkEvidence } from "@/lib/link-evidence";

const lineage = (row: number) => ({
  source_file: "synthetic.xlsx", sheet: "Statement", row_number: row,
  raw_hash: "a".repeat(64), run_id: "run-synthetic", mapping_version: "synthetic-v1",
});

function link(row: number, amount: string | null = "12.34", policy = `P-${row}`): LinkEvidence {
  return {
    schema_version: 1, lineage: lineage(row), state: "provisional", reason: "name_dob_only",
    policy_id: null, amount,
    candidates: [{ policy_id: policy, methods: ["NAME_DOB"], lineage: lineage(row + 100) }],
  };
}

describe("LinkEvidencePanel", () => {
  it("distinguishes an absent artifact from a present empty artifact", () => {
    const { rerender } = render(<LinkEvidencePanel />);
    const region = () => screen.getByRole("region", { name: "Policy link evidence" });
    const missingArtifactCopy = region().textContent;
    expect(region()).toHaveTextContent("No policy link evidence artifact is attached to this run.");
    rerender(<LinkEvidencePanel links={[]} />);
    expect(region()).toHaveTextContent(/artifact contains no policy link records/i);
    expect(region().textContent).not.toBe(missingArtifactCopy);
  });

  it("shows a provisional candidate without selecting a policy and preserves both lineages", () => {
    render(<LinkEvidencePanel links={[link(4, "12.34", "P-CANDIDATE")]} />);
    const table = screen.getByRole("table", { name: "Statement lines and candidate policies" });
    const row = within(table).getByRole("row", { name: /synthetic\.xlsx/ });
    expect(row).toHaveTextContent("provisional");
    expect(row).toHaveTextContent("$12.34");
    expect(within(row).getByText("None confirmed")).toBeInTheDocument();
    expect(within(row).getByText("synthetic.xlsx, Statement, row 4")).toBeInTheDocument();
    fireEvent.click(within(row).getByText(/source and candidates/i));
    const candidate = within(row).getByText("P-CANDIDATE").closest("li");
    expect(candidate).not.toBeNull();
    const evidence = within(candidate as HTMLElement);
    expect(evidence.getByText("synthetic.xlsx")).toBeInTheDocument();
    expect(evidence.getByText("Statement, 104")).toBeInTheDocument();
    expect(evidence.getByText("run-synthetic")).toBeInTheDocument();
    expect(evidence.getByText("synthetic-v1")).toBeInTheDocument();
    expect(evidence.getByText("a".repeat(64))).toBeInTheDocument();
  });

  it("keeps signed negative amounts and does not render a null amount as zero", () => {
    render(<LinkEvidencePanel links={[link(1, "-2.50"), link(2, null)]} />);
    expect(screen.getByText("-$2.50")).toBeInTheDocument();
    expect(screen.getByText("Not reported")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("counts all 26 records and pages to the final candidate evidence", () => {
    const links = Array.from({ length: 26 }, (_, i) => link(i + 1, "1.00", `P-${i + 1}`));
    render(<LinkEvidencePanel links={links} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Page 1 of 2; showing 25 of 26 records/);
    expect(screen.queryByText("P-26")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/Page 2 of 2; showing 1 of 26 records/);
    const lastRow = screen.getByRole("row", { name: /row 26/ });
    fireEvent.click(within(lastRow).getByText(/source and candidates/i));
    expect(within(lastRow).getByText("P-26")).toBeInTheDocument();
  });
});
