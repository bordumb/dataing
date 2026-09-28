/**
 * The LLM status banner (spec 0001 §8.4): under the header on every page
 * while the API's key check reports a problem, naming it and what to fix.
 * It can't be dismissed; it goes away when the problem does.
 */

import { AlertTriangle } from "lucide-react";

import { useLlmStatus } from "@/lib/api/system";
import { cn } from "@/lib/utils";

/** Nothing to report. */
const QUIET = new Set(["ok", "checking"]);

/** Problems a retry can outlast; everything else needs someone to fix it. */
const TRANSIENT = new Set([
  "unreachable",
  "rate_limited",
  "overloaded",
  "server_error",
]);

export function LlmStatusBanner() {
  const { data } = useLlmStatus();
  if (!data || QUIET.has(data.state)) return null;
  const transient = TRANSIENT.has(data.state);

  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2.5 border-b px-4 py-2.5 text-sm",
        transient
          ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          : "border-destructive/30 bg-destructive/10 text-destructive dark:bg-destructive/20 dark:text-red-300",
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
      <p>
        <span className="font-semibold">
          {data.message || "The LLM isn't working."}
        </span>{" "}
        {transient
          ? "Investigations and agent answers may be slow or fail until it recovers."
          : "Investigations and the agent can't run until this is fixed."}
      </p>
    </div>
  );
}
