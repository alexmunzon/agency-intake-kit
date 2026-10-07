import { readFileSync } from "node:fs";
import path from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MappingReviewPanel } from "@/components/mapping-review-panel";
import { Sources } from "@/components/sources";
import { parseMappingReview, type MappingReviewState } from "@/lib/mapping-review";
import { loadRunDir } from "@/lib/run-dir";

const TEXT = readFileSync(path.resolve(import.meta.dirname, "../../lib/__tests__/fixtures/mapping-review.json"), "utf8");
const review = parseMappingReview(TEXT, "demo");
const STATE: MappingReviewState = { ok: true, review };
const AT = "2026-10-06T12:00:00.000Z";

function setup(state: MappingReviewState = STATE) {
  const download = vi.fn<(fileName: string, text: string) => void>();
  render(<MappingReviewPanel state={state} now={() => AT} download={download} />);
  return download;
}
const card = (header: string) => screen.getByRole("article", { name: new RegExp(`^Column ${header}, `) });
const typeName = (name: string) => fireEvent.change(screen.getByLabelText("Reviewer name"), { target: { value: name } });
const downloadButton = () => screen.getByRole("button", { name: "Download decisions" });
const saved = (download: ReturnType<typeof setup>) => JSON.parse(download.mock.calls[0][1]);

afterEach(() => vi.restoreAllMocks());

describe("MappingReviewPanel", () => {
  it("shows one card per item with the evidence a reviewer needs", () => {
    setup();
    expect(screen.getAllByRole("article")).toHaveLength(3);
    const premium = within(card("Prem Amt"));
    expect(premium.getByText("crm_export.csv")).toBeInTheDocument();
    expect(premium.getByText("1**.**")).toBeInTheDocument();
    expect(premium.getByText("policies.premium", { selector: "code" })).toBeInTheDocument();
    expect(premium.getByText("Jev (replay)")).toBeInTheDocument();
    expect(premium.getByText("72%")).toBeInTheDocument();
    expect(premium.getByText(/model's confidence, not measured accuracy/)).toBeInTheDocument();
    expect(premium.getByText("2,600")).toBeInTheDocument();
    expect(premium.getByText("MAP-002:crm:Prem Amt")).toBeInTheDocument();
    expect(premium.getByText(/below the 0.85 needed/)).toBeInTheDocument();

    const notes = within(card("Agent Remarks"));
    expect(notes.getByText("Samples withheld: this column may hold notes or ID numbers")).toBeInTheDocument();
    expect(notes.getByText("No model answer")).toBeInTheDocument();
    expect(notes.getByText(/may hold notes, so its values were not sent to Jev/)).toBeInTheDocument();
    expect(within(card("Comm Pd")).getByText(/too low/)).toBeInTheDocument();
  });

  it("keeps low-confidence explanations, citations and review warnings visible", () => {
    setup();
    const premium = within(card("Prem Amt"));
    for (const text of ["MAP-002:crm:Prem Amt", "72%", "crm_export.csv"]) expect(premium.getByText(text)).toBeVisible();
    expect(premium.getByText(/below the 0.85 needed/)).toBeVisible();
    expect(premium.getByRole("radio", { name: "Leave unresolved" })).toBeVisible();
    expect(screen.getByText("A reviewer's note, not an authenticated approval")).toBeVisible();
    expect(within(card("Agent Remarks")).getByText(/may hold notes, so its values were not sent to Jev/)).toBeVisible();
  });

  it("labels live and recorded answers differently from replay", () => {
    const items = review.items.map((item, i) => (i === 1 ? { ...item, origin: "jev_live" as const } : i === 2 ? { ...item, origin: "jev_record" as const } : item));
    setup({ ok: true, review: { ...review, items } });
    expect(within(card("Prem Amt")).getByText("Jev (live)")).toBeInTheDocument();
    expect(within(card("Comm Pd")).getByText("Jev (record)")).toBeInTheDocument();
  });

  it("defaults every card to leave unresolved and disables approve with no proposal", () => {
    setup();
    for (const header of ["Agent Remarks", "Prem Amt", "Comm Pd"]) {
      expect(within(card(header)).getByRole("radio", { name: "Leave unresolved" })).toBeChecked();
    }
    expect(within(card("Agent Remarks")).getByRole("radio", { name: /Approve/ })).toBeDisabled();
    expect(within(card("Prem Amt")).getByRole("radio", { name: /Approve/ })).toBeEnabled();
  });

  it("offers only the item's allowed fields when correcting, never none", () => {
    setup();
    const premium = within(card("Prem Amt"));
    fireEvent.click(premium.getByRole("radio", { name: "Correct to another field" }));
    const options = within(premium.getByLabelText("Correct field for Prem Amt")).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(options).toEqual(["", "policies.premium", "policies.plan_id", "clients.zip"]);
  });

  it("downloads approve, correct and ignore decisions and leaves the rest out", () => {
    const download = setup();
    fireEvent.click(within(card("Prem Amt")).getByRole("radio", { name: /Approve/ }));
    const paid = within(card("Comm Pd"));
    fireEvent.click(paid.getByRole("radio", { name: "Correct to another field" }));
    fireEvent.change(paid.getByLabelText("Correct field for Comm Pd"), { target: { value: "commission_lines.policy_id" } });
    fireEvent.click(within(card("Agent Remarks")).getByRole("radio", { name: "Ignore this column" }));
    typeName("  Dana Reviewer  ");
    fireEvent.click(downloadButton());
    expect(download).toHaveBeenCalledTimes(1);
    expect(download.mock.calls[0][0]).toBe("mapping-decisions-demo.json");
    const file = saved(download);
    expect(Object.keys(file)).toEqual(["run_id", "mapping_version", "reviewer", "decided_at", "note", "decisions"]);
    expect(file).toMatchObject({ run_id: "demo", reviewer: "Dana Reviewer", decided_at: AT,
      note: "a reviewer's note, not an authenticated approval" });
    expect(file.decisions.map((d: { action: string; field: string | null }) => [d.action, d.field])).toEqual([
      ["ignore", null], ["approve", "policies.premium"], ["correct", "commission_lines.policy_id"]]);
  });

  it("switching back to leave unresolved removes the decision", () => {
    const download = setup();
    const premium = within(card("Prem Amt"));
    fireEvent.click(premium.getByRole("radio", { name: /Approve/ }));
    fireEvent.click(premium.getByRole("radio", { name: "Ignore this column" }));
    fireEvent.click(premium.getByRole("radio", { name: "Leave unresolved" }));
    fireEvent.click(within(card("Comm Pd")).getByRole("radio", { name: /Approve/ }));
    typeName("Dana");
    fireEvent.click(downloadButton());
    expect(saved(download).decisions.map((d: { header: string }) => d.header)).toEqual(["Comm Pd"]);
  });

  it("requires a reviewer name before downloading", () => {
    const download = setup();
    fireEvent.click(within(card("Prem Amt")).getByRole("radio", { name: /Approve/ }));
    typeName("   ");
    fireEvent.click(downloadButton());
    expect(download).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Type your name before downloading.");
  });

  it("asks for at least one decision before downloading", () => {
    const download = setup();
    typeName("Dana");
    fireEvent.click(downloadButton());
    expect(download).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/at least one decision/);
  });

  it("labels the download area as a reviewer's note", () => {
    setup();
    expect(screen.getByRole("group", { name: "A reviewer's note, not an authenticated approval" })).toBeInTheDocument();
  });

  it("saves through a browser download by default and sends nothing over the network", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob) => { blobs.push(blob); return "blob:decisions"; });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<MappingReviewPanel state={STATE} now={() => AT} />);
    fireEvent.click(within(card("Prem Amt")).getByRole("radio", { name: /Approve/ }));
    typeName("Dana");
    fireEvent.click(downloadButton());
    expect(click).toHaveBeenCalledTimes(1);
    expect(JSON.parse(await blobs[0].text()).note).toBe("a reviewer's note, not an authenticated approval");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows one line when nothing needs review", () => {
    setup({ ok: true, review: { ...review, items: [] } });
    expect(screen.getByText("Every column was mapped by the dictionary or a saved decision.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download decisions" })).toBeNull();
  });

  it("shows a plain error for a malformed file", () => {
    setup({ ok: false, error: "mapping_review.json: expected an object" });
    expect(screen.getByRole("alert")).toHaveTextContent("mapping_review.json: expected an object");
    expect(screen.queryByRole("article")).toBeNull();
  });

  it("words each reason plainly and says when a column simply had no values", () => {
    const items = [
      { ...review.items[1], reason: "http_error", route: "person" as const, proposed_field: null, origin: "none" as const, confidence: null },
      { ...review.items[2], reason: "field_taken", samples: [], samples_withheld: false },
    ];
    setup({ ok: true, review: { ...review, items } });
    expect(within(card("Prem Amt")).getByText(/Jev returned an error/)).toBeInTheDocument();
    const paid = within(card("Comm Pd"));
    expect(paid.getByText(/Another column already holds this field/)).toBeInTheDocument();
    expect(paid.getByText("No values to sample")).toBeInTheDocument();
    expect(paid.queryByText(/Samples withheld/)).toBeNull();
    expect(screen.queryByText(/field taken/)).toBeNull();
  });

  it("does not let the browser autofill the reviewer name", () => {
    setup();
    expect(screen.getByLabelText("Reviewer name")).toHaveAttribute("autocomplete", "off");
  });

  it("warns and does not download when two columns of one source get the same field", () => {
    const second = { ...review.items[1], item_id: "mr-aaaaaaaaaaaa", header: "Premium Two" };
    const download = setup({ ok: true, review: { ...review, items: [...review.items, second] } });
    fireEvent.click(within(card("Prem Amt")).getByRole("radio", { name: /Approve/ }));
    fireEvent.click(within(card("Premium Two")).getByRole("radio", { name: /Approve/ }));
    typeName("Dana");
    expect(screen.getByText(/Two columns in crm are set to policies.premium/)).toBeInTheDocument();
    fireEvent.click(downloadButton());
    expect(download).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/Two columns in crm are set to policies.premium/);
  });

  it("warns when the same column in two files gets different decisions", () => {
    const feb = { ...review.items[1], item_id: "mr-bbbbbbbbbbbb", file_name: "crm_feb.csv" };
    const download = setup({ ok: true, review: { ...review, items: [...review.items, feb] } });
    const [jan, february] = screen.getAllByRole("article", { name: /^Column Prem Amt, / });
    fireEvent.click(within(jan).getByRole("radio", { name: /Approve/ }));
    fireEvent.click(within(february).getByRole("radio", { name: "Ignore this column" }));
    typeName("Dana");
    fireEvent.click(downloadButton());
    expect(download).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/Prem Amt in crm has different decisions in two files/);
  });

  it("renders nothing when the run has no review file", () => {
    const { container } = render(<MappingReviewPanel state={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Sources page", () => {
  it("adds the review panel only when the run has a review file", async () => {
    const run = await loadRunDir(path.resolve(import.meta.dirname, "../../../fixtures/sample-run"));
    const view = render(<Sources run={run} />);
    expect(screen.queryByRole("region", { name: "Column mapping review" })).toBeNull();
    view.rerender(<Sources run={run} mappingReview={STATE} />);
    expect(screen.getByRole("region", { name: "Column mapping review" })).toBeInTheDocument();
  });
});
