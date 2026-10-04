import type { Metadata } from "next";

import { TieOutView } from "@/components/tie-out";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";
import { loadTieOut } from "@/lib/tie-out";

export const metadata: Metadata = { title: "Tie-out | Agency Intake Kit" };

// Read at build time from public/demo-run. The dashboard makes no network calls.
export default async function TieOutPage() {
  return <TieOutView run={await loadRunDir(DEMO_RUN_DIR)} tieOut={await loadTieOut(DEMO_RUN_DIR)} />;
}
