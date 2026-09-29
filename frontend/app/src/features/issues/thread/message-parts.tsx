/**
 * Pieces every thread entry shares: the time stamp, the avatar and the meta
 * line ("Maya · asked the agent · 08:10").
 */

import { format, isToday } from "date-fns";

import { cn } from "@/lib/utils";

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return isToday(date) ? format(date, "HH:mm") : format(date, "MMM d, HH:mm");
}

const AVATAR_COLORS = [
  "bg-sky-500",
  "bg-orange-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-indigo-500",
];

export function colorFor(key: string): string {
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export function Avatar({
  label,
  className,
}: {
  label: string;
  className: string;
}) {
  return (
    <div
      aria-hidden
      className={cn(
        "grid h-7 w-7 flex-none place-items-center rounded-full text-xs font-bold text-white",
        className,
      )}
    >
      {label}
    </div>
  );
}

/** dataing's own entries: runs it started and issues it opened. */
export const SYSTEM_AVATAR = "bg-zinc-500";

/** Blue text links, as in the mockup ("view brief", "details →"). */
export const LINK_CLASS = "text-blue-600 hover:underline dark:text-blue-400";

export function Meta({ children }: { children: React.ReactNode }) {
  return <div className="mb-0.5 text-xs text-muted-foreground">{children}</div>;
}
