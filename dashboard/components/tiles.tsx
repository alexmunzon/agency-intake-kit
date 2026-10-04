import { SeverityIcon, type Tone } from "@/components/severity-badge";
import { cn } from "@/lib/utils";

export const CARD = "rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";

interface TileProps {
  label: string;
  value: string;
  context?: string;
  tone?: Tone;
  /** Shown flat and gray when the run never reached this check. */
  muted?: boolean;
}

export function Tile({ label, value, context, tone, muted }: TileProps) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(CARD, "p-4", muted && "border-dashed bg-slate-100 dark:bg-slate-950")}
    >
      <p className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400">
        {tone && !muted && <SeverityIcon tone={tone} />}
        {label}
      </p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", muted && "text-slate-600 dark:text-slate-400")}>
        {value}
      </p>
      {context && <p className="mt-1 text-xs text-slate-600 tabular-nums dark:text-slate-400">{context}</p>}
    </div>
  );
}
