import { CircleAlert, CircleCheck, Info, OctagonX, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

// Fixed meanings. Color is never the only signal: every tone has an icon and a word.
export type Tone = "blocker" | "error" | "warning" | "info" | "pass";

export const TONES: Record<Tone, { label: string; icon: LucideIcon; color: string; band: string }> = {
  blocker: { label: "Blocker", icon: OctagonX, color: "status-error", band: "bg-muted-foreground" },
  error: { label: "Error", icon: TriangleAlert, color: "status-error", band: "bg-muted-foreground" },
  warning: { label: "Warning", icon: CircleAlert, color: "status-warning", band: "bg-muted-foreground" },
  info: { label: "Info", icon: Info, color: "text-muted-foreground", band: "bg-muted-foreground" },
  pass: { label: "Pass", icon: CircleCheck, color: "status-pass", band: "bg-muted-foreground" },
};

export function SeverityIcon({ tone, className }: { tone: Tone; className?: string }) {
  const Icon = TONES[tone].icon;
  return <Icon aria-hidden className={cn("size-4 shrink-0", TONES[tone].color, className)} />;
}

export function SeverityBadge({ tone, label }: { tone: Tone; label?: string }) {
  return (
    <span className="severity-badge inline-flex items-center gap-1 rounded-md border border-border px-1.5 py-0.5 text-xs font-medium">
      <SeverityIcon tone={tone} className="size-3.5" />
      {label ?? TONES[tone].label}
    </span>
  );
}
