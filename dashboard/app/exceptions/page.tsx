import type { Metadata } from "next";

import { ExceptionsView } from "@/components/exceptions-view";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";

export const metadata: Metadata = { title: "Exceptions | Agency Intake Kit" };

// Read at build time. Filtering and the drawer run in the browser on data already on the page.
export default async function ExceptionsPage() {
  const run = await loadRunDir(DEMO_RUN_DIR);
  return (
    <div className="space-y-4">
      <header>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Run <span className="font-mono text-xs">{run.manifest.run_id}</span>. Synthetic data only.
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">What needs fixing, in what order, and how?</h1>
        <p className="mt-1 text-sm">Blockers come first. Select a row to see where it came from and how to fix it.</p>
      </header>
      <ExceptionsView records={run.exceptions} />
    </div>
  );
}
