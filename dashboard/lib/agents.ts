import type { RtsCell, RtsCoverage } from "@/lib/types";

// Shapes rts_coverage.json into a matrix: one row per writing agent (NPN), one column per
// carrier, state, and plan year. A missing cell means the roster shows no RTS and no sales there.
export interface MatrixColumn {
  label: string;
  carrier: string;
  state: string;
  year: number;
}

export interface AgentRow {
  npn: string;
  cells: Map<string, RtsCell>;
  policies: number;
  held: number;
  gaps: number;
}

export interface RtsMatrix {
  columns: MatrixColumn[];
  agents: AgentRow[];
  /** Policies sold without RTS, one RTS-001 each. The number the Overview and report show (#76). */
  gapPolicies: number;
  /** Agent, carrier, state, and year cells with a gap. Shown only beside the matrix. */
  gapCells: number;
}

const label = (cell: RtsCell) => `${cell.carrier} ${cell.state} ${cell.plan_year}`;

export function rtsMatrix(coverage: RtsCoverage): RtsMatrix {
  const columns = new Map<string, MatrixColumn>();
  const agents = new Map<string, AgentRow>();
  let gapPolicies = 0;
  let gapCells = 0;
  for (const cell of coverage.cells) {
    columns.set(label(cell), { label: label(cell), carrier: cell.carrier, state: cell.state, year: cell.plan_year });
    const row = agents.get(cell.npn) ?? { npn: cell.npn, cells: new Map(), policies: 0, held: 0, gaps: 0 };
    row.cells.set(label(cell), cell);
    row.policies += cell.policy_count;
    if (cell.coverage === "USED_WITHOUT_RTS") {
      row.gaps += 1;
      gapCells += 1;
      gapPolicies += cell.policy_count;
    } else {
      row.held += 1;
    }
    agents.set(cell.npn, row);
  }
  const byColumn = (a: MatrixColumn, b: MatrixColumn) =>
    a.carrier.localeCompare(b.carrier) || a.state.localeCompare(b.state) || a.year - b.year;
  return {
    columns: [...columns.values()].sort(byColumn),
    agents: [...agents.values()].sort((a, b) => a.npn.localeCompare(b.npn)),
    gapPolicies,
    gapCells,
  };
}
