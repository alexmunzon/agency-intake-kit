"use client";

import { tableFeatures, useTable, type ColumnDef, type RowData } from "@tanstack/react-table";

import { CARD } from "@/components/tiles";
import { cn } from "@/lib/utils";

// A dense table with a sticky header and, on narrow screens, a sticky first column so a row
// keeps its label while the rest scrolls sideways. Filtering happens before the data arrives.
export const features = tableFeatures({});
export type Columns<T extends RowData> = ColumnDef<typeof features, T>[];

interface DataTableProps<T extends RowData> {
  label: string;
  columns: Columns<T>;
  data: T[];
  rowLabel: (row: T) => string;
  onRowClick: (row: T) => void;
}

const STICKY = "sticky left-0 z-10 bg-white dark:bg-slate-900";

export function DataTable<T extends RowData>({ label, columns, data, rowLabel, onRowClick }: DataTableProps<T>) {
  const table = useTable({ features, columns, data });
  return (
    <div className={cn(CARD, "max-h-[70vh] overflow-auto")}>
      <table aria-label={label} className="w-full min-w-[720px] text-left text-xs tabular-nums">
        <thead className="sticky top-0 z-20 bg-slate-50 dark:bg-slate-950">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header, index) => (
                <th key={header.id} scope="col" className={cn("px-3 py-2 font-medium", index === 0 && "sticky left-0 z-10 bg-slate-50 dark:bg-slate-950")}>
                  <table.FlexRender header={header} />
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              tabIndex={0}
              aria-label={rowLabel(row.original)}
              onClick={() => onRowClick(row.original)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onRowClick(row.original);
                }
              }}
              className="h-9 cursor-pointer border-t border-slate-200 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-800 dark:hover:bg-slate-800"
            >
              {row.getAllCells().map((cell, index) => (
                <td key={cell.id} className={cn("px-3 py-1.5 align-top", index === 0 && STICKY)}>
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
