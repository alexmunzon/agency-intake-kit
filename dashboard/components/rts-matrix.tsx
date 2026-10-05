import { SeverityIcon, type Tone } from "@/components/severity-badge";
import { STICKY, TABLE, TABLE_WRAP } from "@/components/tie-out";
import type { RtsMatrix } from "@/lib/agents";
import { plural } from "@/lib/overview";
import type { RtsCellState } from "@/lib/types";
import { cn } from "@/lib/utils";

// Each state has an icon and a word, so the matrix reads without color.
export const CELL_STATES: Record<RtsCellState, { label: string; tone: Tone; meaning: string }> = {
  HELD_AND_USED: { label: "Held and used", tone: "pass", meaning: "Ready to sell, and sold" },
  HELD_UNUSED: { label: "Held but unused", tone: "info", meaning: "Ready to sell, nothing sold yet" },
  USED_WITHOUT_RTS: { label: "Used without RTS", tone: "error", meaning: "Sold before being ready to sell" },
};

const policies = (count: number) => `${count.toLocaleString("en-US")} ${count === 1 ? "policy" : "policies"}`;

export function RtsMatrixTable({ matrix }: { matrix: RtsMatrix }) {
  return (
    <div className="space-y-2">
      <ul aria-label="What the cells mean" className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {Object.values(CELL_STATES).map(({ label, tone, meaning }) => (
          <li key={label} className="flex items-center gap-1">
            <SeverityIcon tone={tone} className="size-3.5" />
            <span className="font-medium">{label}:</span> {meaning}
          </li>
        ))}
      </ul>
      <div className={TABLE_WRAP}>
        <table className={TABLE}>
          <caption className="p-3 text-left text-sm font-medium whitespace-normal">
            RTS matrix: agent by carrier, state, and plan year
            {matrix.gapCells > 0 && (
              <span className="block text-xs font-normal text-slate-600 dark:text-slate-400">
                {`Gaps: ${plural(matrix.gapCells, "agent, carrier, state and year combination")}.`}
              </span>
            )}
            <span className="block text-xs font-normal text-slate-600 sm:hidden dark:text-slate-400">Scroll sideways to see every column.</span>
          </caption>
          <thead>
            <tr>
              <th className={STICKY}>Agent (NPN)</th>
              {matrix.columns.map((column) => (
                <th key={column.label}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.agents.map((agent) => (
              <tr key={agent.npn}>
                <th scope="row" className={cn(STICKY, "font-mono")}>{agent.npn}</th>
                {matrix.columns.map((column) => {
                  const cell = agent.cells.get(column.label);
                  const where = `${agent.npn}, ${column.label}`;
                  if (!cell) {
                    return (
                      <td key={column.label} aria-label={`${where}: No RTS and no policies`} className="text-slate-600 dark:text-slate-400">
                        None
                      </td>
                    );
                  }
                  const state = CELL_STATES[cell.coverage];
                  const gap = cell.coverage === "USED_WITHOUT_RTS";
                  return (
                    <td
                      key={column.label}
                      data-state={cell.coverage}
                      aria-label={`${where}: ${state.label}, ${policies(cell.policy_count)}`}
                      className={cn(gap && "bg-orange-50 font-semibold outline-2 -outline-offset-2 outline-orange-600 dark:bg-orange-950")}
                    >
                      <span className="flex items-center gap-1">
                        <SeverityIcon tone={state.tone} className="size-3.5" />
                        {state.label}
                      </span>
                      <span className="block font-normal text-slate-600 dark:text-slate-400">{policies(cell.policy_count)}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
