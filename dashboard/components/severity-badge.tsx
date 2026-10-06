import { CircleAlert, CircleCheck, Info, OctagonX, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

// Fixed meanings. Color is never the only signal: every tone has an icon and a word.
export type Tone = "blocker" | "error" | "warning" | "info" | "pass";

export const TONES: Record<Tone, { label: string; icon: LucideIcon; color: string; band: string }> = {
  blocker: { label: "Blocker", icon: OctagonX, color: "text-rose-600 dark:text-rose-400", band: "bg-rose-600" },
  error: { label: "Error", icon: TriangleAlert, color: "text-orange-600 dark:text-orange-400", band: "bg-orange-600" },
  warning: { label: "Warning", icon: CircleAlert, color: "text-amber-600 dark:text-amber-400", band: "bg-amber-500" },
  info: { label: "Info", icon: Info, color: "text-sky-600 dark:text-sky-400", band: "bg-sky-600" },
  pass: { label: "Pass", icon: CircleCheck, color: "text-emerald-600 dark:text-emerald-400", band: "bg-emerald-600" },
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
