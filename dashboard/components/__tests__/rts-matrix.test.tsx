import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RtsMatrixTable } from "@/components/rts-matrix";
import { rtsMatrix } from "@/lib/agents";
import type { RtsCoverage } from "@/lib/types";

function coverage(count: number): RtsCoverage {
  return { cells: Array.from({ length: count }, (_, index) => ({
    npn: "1884412", carrier: `Carrier ${String(index).padStart(2, "0")}`,
    state: "TX", plan_year: 2026, coverage: "USED_WITHOUT_RTS",
    policy_count: index + 1, exception_ids: [],
  })) };
}

describe("RTS matrix column navigation", () => {
  it("bounds rendering while keeping all combinations and aggregate gaps available", () => {
    render(<RtsMatrixTable matrix={rtsMatrix(coverage(25))} />);
    const table = within(screen.getByRole("table", { name: /RTS matrix/ }));
    expect(table.getAllByRole("columnheader")).toHaveLength(13);
    expect(screen.getByRole("button", { name: "Previous columns" })).toBeDisabled();
    for (let page = 0; page < 3; page++) {
      const first = page * 12;
      const end = Math.min(first + 12, 25);
      expect(screen.getByText(`Columns ${first + 1} to ${end} of 25`)).toBeInTheDocument();
      expect(table.getAllByRole("cell")).toHaveLength(end - first);
      for (let index = first; index < end; index++) {
        const label = `1884412, Carrier ${String(index).padStart(2, "0")} TX 2026: Used without RTS, ${index + 1} ${index === 0 ? "policy" : "policies"}`;
        expect(table.getByRole("cell", { name: label })).toBeInTheDocument();
      }
      if (page < 2) fireEvent.click(screen.getByRole("button", { name: "Next columns" }));
    }
    expect(screen.getByRole("button", { name: "Next columns" })).toBeDisabled();
    expect(table.getByText("Gaps: 25 agent, carrier, state and year combinations.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous columns" }));
    expect(screen.getByText("Columns 13 to 24 of 25")).toBeInTheDocument();
  });

  it("returns to the first columns when a different run matrix arrives", () => {
    const view = render(<RtsMatrixTable matrix={rtsMatrix(coverage(25))} />);
    fireEvent.click(screen.getByRole("button", { name: "Next columns" }));
    view.rerender(<RtsMatrixTable matrix={rtsMatrix(coverage(2))} />);
    expect(screen.getAllByRole("cell")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Next columns" })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1884412, Carrier 00 TX 2026: Used without RTS, 1 policy" })).toBeInTheDocument();
  });
});
