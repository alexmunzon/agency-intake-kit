import { RtsMatrixTable } from "@/components/rts-matrix";
import { SeverityBadge } from "@/components/severity-badge";
import { Answer, PageHeader, STICKY, TABLE, TABLE_WRAP } from "@/components/tie-out";
import { CARD } from "@/components/tiles";
import { rtsMatrix } from "@/lib/agents";
import { plural, rtsChecked } from "@/lib/overview";
import type { Run } from "@/lib/run-loader";
import { cn } from "@/lib/utils";

export function AgentsView({ run }: { run: Run }) {
  const question = "Is every writing agent allowed to sell what they sold?";
  if (!rtsChecked(run)) {
    return (
      <div className="page-stack">
        <PageHeader run={run} question={question} />
        <Answer tone="blocker" text="Not checked. The run stopped before RTS was checked." detail={run.manifest.status_reason} />
      </div>
    );
  }
  const matrix = rtsMatrix(run.rts);
  const records = new Map(run.exceptions.map((record) => [record.id, record]));
  const gaps = matrix.agents.flatMap((agent) =>
    [...agent.cells.values()].filter((cell) => cell.coverage === "USED_WITHOUT_RTS"),
  );
  const count = matrix.gapPolicies;
  return (
    <div className="page-stack">
      <PageHeader run={run} question={question} />
      {count > 0 ? (
        <Answer
          tone="error"
          text={`No. ${count.toLocaleString("en-US")} ${count === 1 ? "policy was" : "policies were"} sold without ready-to-sell status.`}
          detail="RTS means ready to sell: appointed and certified with the carrier for that state and year. These policies are kept out of the load files until fixed."
        />
      ) : (
        <Answer tone="pass" text="Yes. Every policy was written by an agent ready to sell it." />
      )}
      {gaps.length > 0 && (
        <section aria-labelledby="gaps" className={cn(CARD, "p-4")}>
          <h2 id="gaps" className="text-sm font-medium">RTS gaps to fix</h2>
          <ul className="mt-2 space-y-2 text-sm">
            {gaps.flatMap((cell) =>
              cell.exception_ids.map((id) => {
                const record = records.get(id);
                const lineage = record?.lineage;
                return (
                  <li key={id} aria-label={id} className="border-t border-border pt-2 first:border-0 first:pt-0">
                    <p className="flex flex-wrap items-center gap-2">
                      <SeverityBadge tone="error" label="RTS-001" />
                      <span className="font-mono text-xs">{id}</span>
                      <span>Agent <span className="font-mono text-xs">{cell.npn}</span>, {cell.carrier} {cell.state} {cell.plan_year}</span>
                    </p>
                    {lineage && <p className="font-mono text-xs">{`${lineage.source_file} row ${lineage.row_number}`}</p>}
                    {record && <p>{record.message}. Fix: {record.suggested_fix}</p>}
                  </li>
                );
              }),
            )}
          </ul>
        </section>
      )}
      <div role="region" aria-label="Writing agents table" tabIndex={0} className={TABLE_WRAP}>
        <table className={TABLE}>
          <caption className="p-3 text-left text-sm font-medium">Writing agents</caption>
          <thead>
            <tr>
              <th className={STICKY}>Agent (NPN)</th><th>Policies written</th><th>RTS held</th><th>Gaps</th>
            </tr>
          </thead>
          <tbody>
            {matrix.agents.map((agent) => (
              <tr key={agent.npn}>
                <th scope="row" className={cn(STICKY, "font-mono")}>{agent.npn}</th>
                <td>{agent.policies.toLocaleString("en-US")}</td>
                <td>{plural(agent.held, "combination")}</td>
                <td>{agent.gaps > 0 ? <SeverityBadge tone="error" label={plural(agent.gaps, "gap")} /> : <SeverityBadge tone="pass" label="None" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RtsMatrixTable matrix={matrix} />
    </div>
  );
}
