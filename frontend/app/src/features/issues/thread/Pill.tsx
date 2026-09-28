/**
 * Small status pills for thread cards (the mockup's .pill variants).
 */

import { cn } from "@/lib/utils";

export type PillTone = "neutral" | "ok" | "bad" | "warn" | "agent" | "info";

const TONES: Record<PillTone, string> = {
  neutral: "border-border text-muted-foreground",
  ok: "border-transparent bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-400",
  bad: "border-transparent bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-400",
  warn: "border-transparent bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  agent:
    "border-transparent bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  info: "border-transparent bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
};

export function Pill({
  tone = "neutral",
  className,
  children,
}: {
  tone?: PillTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-px text-xs",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Tone and words for a hypothesis status, live or final. */
export const HYPOTHESIS_STATUS: Record<
  string,
  { tone: PillTone; label: string }
> = {
  pending: { tone: "neutral", label: "queued" },
  running: { tone: "agent", label: "testing" },
  supported: { tone: "ok", label: "supported" },
  refuted: { tone: "bad", label: "refuted by evidence" },
  untested: { tone: "warn", label: "untested" },
  ruled_out: { tone: "neutral", label: "ruled out by a person" },
};

export function hypothesisStatus(status: string) {
  return (
    HYPOTHESIS_STATUS[status] ?? { tone: "neutral" as const, label: status }
  );
}
