import { ExceptionsView } from "@/components/exceptions-view";
import { PageHeader } from "@/components/tie-out";
import type { Run } from "@/lib/run-loader";

// Not a client file, so the demo page renders this header on the server and only the
// exception records cross into the browser.
export function ExceptionsPage({ run }: { run: Run }) {
  return (
    <div className="page-stack">
      <PageHeader run={run} question="What needs fixing, in what order, and how?">
        Blockers come first. Select a row to see where it came from and how to fix it.
      </PageHeader>
      <ExceptionsView records={run.exceptions} jevMode={run.manifest.jev.mode} />
    </div>
  );
}
