import type { Metadata } from "next";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { RunFinance } from "@/components/run-finance";
import { parseFinanceReview } from "@/lib/finance-review";

import { LoadRun } from "@/components/load-run";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Runs | Agency Intake Kit" };

export default async function RunsPage() {
  const demo = await loadRunDir(DEMO_RUN_DIR);
  const finance = parseFinanceReview(await readFile(path.join(process.cwd(), "public", "demo-finance.json"), "utf8"));
  return <><LoadRun demoRunId={demo.manifest.run_id} /><RunFinance example={finance} /></>;
}
