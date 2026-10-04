import { describe, expect, it } from "vitest";

import { formatMoney, sumMoney } from "@/lib/money";

describe("formatMoney", () => {
  it.each([
    ["61.05", "$61.05"],
    ["1234567.50", "$1,234,567.50"],
    ["-24.50", "-$24.50"],
    ["0.000901", "$0.000901"],
  ])("formats %s as %s", (text, shown) => {
    expect(formatMoney(text)).toBe(shown);
  });

  it.each(["61.0.5", "1e3", "", "$5.00"])("refuses %j", (text) => {
    expect(() => formatMoney(text)).toThrow(/money/);
  });
});

describe("sumMoney", () => {
  it("adds exactly, with no float drift", () => {
    expect(sumMoney(["0.10", "0.20"])).toBe("0.30");
    expect(sumMoney(["24.50", "61.05", "0.00"])).toBe("85.55");
    expect(sumMoney(["-24.50", "61.05"])).toBe("36.55");
    expect(sumMoney(["-61.05", "24.50"])).toBe("-36.55");
  });

  it("returns zero for an empty list", () => {
    expect(sumMoney([])).toBe("0.00");
  });
});
