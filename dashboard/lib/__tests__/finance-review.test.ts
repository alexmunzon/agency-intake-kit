import { describe, expect, it } from "vitest";
import { parseFinanceReview, type FinanceReview, type FinanceReviewRow } from "@/lib/finance-review";

type MutableReview = Record<string, unknown>;

const HASH = "a".repeat(64);

function row(
  rowId: string,
  amount: string,
  rawAmount = amount,
  transactionLabel = "Pay",
): FinanceReviewRow {
  return {
    row_id: rowId,
    amount,
    raw_amount: rawAmount,
    raw_category_label: "Renewal",
    raw_transaction_label: transactionLabel,
    lineage: {
      source_file: "synthetic-statement.csv",
      sheet: null,
      row_number: rowId === "row-1" ? 2 : 3,
      raw_hash: HASH,
      run_id: "synthetic-run",
      mapping_version: "v1",
    },
    category: "renewal",
    transaction_kind: transactionLabel === "Reverse" ? "reversal" : "payment",
    classification_method: "approved_mapping",
    unresolved_reasons: [],
    account_code: "4100",
    authoritative_policy_id: null,
  };
}

function artifact(): FinanceReview {
  return {
    artifact_type: "neutral_finance_review",
    schema_version: 1,
    agency_id: "agency-synthetic",
    carrier: "Synthetic Carrier",
    period: "2026-09",
    statement_id: "statement-synthetic",
    revision_id: "revision-1",
    content_sha256: HASH,
    mapping_id: "mapping-synthetic",
    mapping_version: "v1",
    mapping_approved: true,
    approved_by: "Synthetic Reviewer",
    approved_at: "2026-10-05T12:00:00Z",
    mapping_snapshot: {
      mapping_id: "mapping-synthetic",
      carrier: "Synthetic Carrier",
      version: "v1",
      approved_by: "Synthetic Reviewer",
      approved_at: "2026-10-05T12:00:00Z",
      categories: { Renewal: "renewal" },
      transaction_kinds: { Pay: "payment", Reverse: "reversal" },
      accounts: { renewal: "4100" },
    },
    mapping_sha256: HASH,
    rows: [row("row-1", "9007199254740993.17"), row("row-2", "-0.01", "-0.01", "Reverse")],
    category_totals: {
      new_business: "0.00",
      renewal: "9007199254740993.16",
      override: "0.00",
      bonus: "0.00",
      marketing: "0.00",
      unclassified: "0.00",
    },
    statement_total: "9007199254740993.16",
    control_total: "9007199254740993.16",
    total_check: "PASS",
  };
}

function artifactWithUnknownLabel(field: "category" | "transaction", label: string): FinanceReview {
  const source = artifact();
  const categoryUnknown = field === "category";
  const mappedCategory = categoryUnknown ? "unclassified" : "renewal";
  source.rows = [{
    ...source.rows[0],
    row_id: "row-unknown-label",
    amount: "0.01",
    raw_amount: "0.01",
    raw_category_label: categoryUnknown ? label : "Renewal",
    raw_transaction_label: categoryUnknown ? "Pay" : label,
    category: mappedCategory,
    transaction_kind: categoryUnknown ? "payment" : null,
    classification_method: "unresolved",
    unresolved_reasons: categoryUnknown
      ? ["unknown_category_label", "missing_account_mapping"]
      : ["unknown_transaction_label"],
    account_code: categoryUnknown ? null : "4100",
  }];
  source.category_totals = {
    new_business: "0.00",
    renewal: mappedCategory === "renewal" ? "0.01" : "0.00",
    override: "0.00",
    bonus: "0.00",
    marketing: "0.00",
    unclassified: mappedCategory === "unclassified" ? "0.01" : "0.00",
  };
  source.statement_total = "0.01";
  source.control_total = "0.01";
  source.total_check = "PASS";
  return source;
}

function altered(change: (value: MutableReview) => void) {
  const value = structuredClone(artifact()) as unknown as MutableReview;
  change(value);
  return value;
}

const invalidStates: Array<[string, (value: MutableReview) => void]> = [
  ["unsupported schema version", (value) => { value.schema_version = 2; }],
  ["unknown total check state", (value) => { value.total_check = "PENDING"; }],
  ["unknown classification state", (value) => { (value.rows as Array<Record<string, unknown>>)[0].classification_method = "suggested"; }],
];

const invalidProvenance: Array<[string, (value: MutableReview) => void]> = [
  ["missing lineage", (value) => { delete (value.rows as Array<Record<string, unknown>>)[0].lineage; }],
  ["missing row hash provenance", (value) => { delete ((value.rows as Array<Record<string, unknown>>)[0].lineage as Record<string, unknown>).raw_hash; }],
  ["invalid source row number", (value) => { ((value.rows as Array<Record<string, unknown>>)[0].lineage as Record<string, unknown>).row_number = 0; }],
];

const malformedRows: Array<[string, (value: MutableReview) => void]> = [
  ["non-array rows", (value) => { value.rows = {}; }],
  ["numeric amount", (value) => { ((value.rows as Array<Record<string, unknown>>)[0]).amount = 0.1; }],
  ["duplicate row IDs", (value) => { const rows = value.rows as Array<Record<string, unknown>>; rows[1].row_id = rows[0].row_id; }],
];

const inheritedLabelCases: Array<[string, "category" | "transaction", string]> = [
  ["category constructor", "category", "constructor"],
  ["category toString", "category", "toString"],
  ["category __proto__", "category", "__proto__"],
  ["transaction constructor", "transaction", "constructor"],
  ["transaction toString", "transaction", "toString"],
  ["transaction __proto__", "transaction", "__proto__"],
];

describe("parseFinanceReview", () => {
  it("accepts JSON and preserves exact decimal strings beyond JavaScript number precision", () => {
    const source = artifact();
    const parsed = parseFinanceReview(JSON.stringify(source));

    expect(parsed.rows.map(({ amount }) => amount)).toEqual([
      "9007199254740993.17",
      "-0.01",
    ]);
    expect(parsed.category_totals.renewal).toBe("9007199254740993.16");
    expect(parsed.statement_total).toBe("9007199254740993.16");
    expect(parsed.control_total).toBe("9007199254740993.16");
    expect(typeof parsed.statement_total).toBe("string");
  });

  it("rejects duplicate keys at the top level", () => {
    const raw = JSON.stringify(artifact()).replace(
      "{",
      '{"artifact_type":"forged",',
    );

    expect(() => parseFinanceReview(raw)).toThrow();
  });

  it("rejects duplicate keys inside nested objects", () => {
    const raw = JSON.stringify(artifact()).replace(
      '"categories":{"Renewal":"renewal"}',
      '"categories":{"Renewal":"renewal","Renewal":"unclassified"}',
    );

    expect(() => parseFinanceReview(raw)).toThrow();
  });

  it("rejects escaped spellings of duplicate keys", () => {
    const raw = JSON.stringify(artifact()).replace(
      '"categories":{"Renewal":"renewal"}',
      '"categories":{"Renewal":"renewal","Ren\\u0065wal":"renewal"}',
    );

    expect(() => parseFinanceReview(raw)).toThrow();
  });

  it("accepts colons, escaped quotes, and backslashes inside ordinary strings", () => {
    const source = artifact();
    source.agency_id = 'Agency: "West" \\ section';

    expect(parseFinanceReview(JSON.stringify(source)).agency_id).toBe(source.agency_id);
  });

  it.each(inheritedLabelCases)("retains %s as unresolved", (_description, field, label) => {
    const parsed = parseFinanceReview(JSON.stringify(artifactWithUnknownLabel(field, label)));
    const [parsedRow] = parsed.rows;

    expect(parsedRow.classification_method).toBe("unresolved");
    if (field === "category") {
      expect(parsedRow.raw_category_label).toBe(label);
      expect(parsedRow.category).toBe("unclassified");
      expect(parsedRow.unresolved_reasons).toEqual([
        "unknown_category_label",
        "missing_account_mapping",
      ]);
    } else {
      expect(parsedRow.raw_transaction_label).toBe(label);
      expect(parsedRow.category).toBe("renewal");
      expect(parsedRow.transaction_kind).toBeNull();
      expect(parsedRow.unresolved_reasons).toEqual(["unknown_transaction_label"]);
    }
  });

  it.each(invalidStates)("rejects %s", (_description, change) => {
    expect(() => parseFinanceReview(altered(change))).toThrow();
  });

  it.each(invalidProvenance)("fails closed on %s", (_description, change) => {
    expect(() => parseFinanceReview(altered(change))).toThrow();
  });

  it.each(malformedRows)("rejects malformed rows: %s", (_description, change) => {
    expect(() => parseFinanceReview(altered(change))).toThrow();
  });
});
