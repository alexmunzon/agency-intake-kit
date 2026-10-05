"use client";

import { FinanceReviewPanel } from "@/components/finance-review-panel";
import { useLoadedRun } from "@/components/loaded-run";
import type { FinanceReview } from "@/lib/finance-review";

export function RunFinance({ example }: { example: FinanceReview }) {
  const { loaded } = useLoadedRun();
  if (loaded && !loaded.finance) return <p className="mt-8 text-sm">This run has no finance.json review attached.</p>;
  const review = loaded?.finance ?? example;
  return <div className="mt-10 space-y-4">
    <p className="text-sm text-slate-600 dark:text-slate-400">{loaded
      ? "Finance evidence attached to the imported package. Review its agency and statement scope."
      : "Separate synthetic finance example, not revenue from the book demo above."}</p>
    {!loaded && <a className="text-sm underline" href="/demo-finance.json" download="finance.json">Download the example finance review JSON</a>}
    <FinanceReviewPanel statements={[review]} />
  </div>;
}
