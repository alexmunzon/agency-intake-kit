import { SeverityIcon, type Tone } from "@/components/severity-badge";
import { cn } from "@/lib/utils";

export const CARD = "consulting-panel rounded-lg bg-card";

interface TileProps {
  label: string;
  value: string;
  context?: string;
  note?: string;
  tone?: Tone;
  /** Shown flat and gray when the run never reached this check. */
  muted?: boolean;
}

export function Tile({ label, value, context, note, tone, muted }: TileProps) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(CARD, "metric-tile p-4", muted && "border-dashed bg-muted dark:bg-muted")}
    >
      <p className="metric-label flex items-center gap-1.5 text-muted-foreground">
        {tone && !muted && <SeverityIcon tone={tone} />}
        {label}
      </p>
      <p className={cn("metric-value mt-1 font-semibold tabular-nums", muted && "text-muted-foreground")}>
        {value}
      </p>
      {context && <p className="metric-context mt-1 text-xs text-muted-foreground tabular-nums">{context}</p>}
      {note && <p className="metric-note mt-2 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}
