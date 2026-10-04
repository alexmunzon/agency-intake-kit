import { Overview } from "@/components/overview";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";
import { loadTieOut } from "@/lib/tie-out";

// Read at build time from public/demo-run. The dashboard makes no network calls.
export default async function OverviewPage() {
  const run = await loadRunDir(DEMO_RUN_DIR);
  return <Overview run={run} tieOut={await loadTieOut(DEMO_RUN_DIR, run)} />;
}
