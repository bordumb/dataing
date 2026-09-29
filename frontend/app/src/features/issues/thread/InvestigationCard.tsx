/**
 * The card for an investigation on the issue ("Investigation #N"): its brief,
 * live phase and the manager's hypotheses as its subagents test them. A run
 * that failed says why (spec 0001 §8.1).
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  asBrief,
  isFailedOutcome,
  isRunning,
  useLiveStatus,
  useSteers,
  type HypothesisState,
  type InvestigationBrief,
  type InvestigationOutcome,
} from "@/lib/api/investigation-runs";
import type { ThreadMessage } from "@/lib/api/issue-threads";
import { runStatus, type InvestigationRunResponse } from "@/lib/api/issues";

import { useIssueHub } from "../hub/hub-context";
import { LINK_CLASS } from "./message-parts";
import { Pill, type PillTone } from "./Pill";
import { Steering } from "./Steering";

export interface InvestigationPayload {
  investigation_id?: string;
  run_id?: string;
  execution_profile?: string;
  brief?: unknown;
  source_thread_id?: string | null;
  parent_run_id?: string | null;
}

const PHASE_LABEL: Record<string, string> = {
  initializing: "starting",
  starting: "starting",
  gather_context: "gathering context",
  check_patterns: "checking known patterns",
  generate_hypotheses: "generating hypotheses",
  evaluate_hypotheses: "evaluating",
  synthesize: "synthesizing",
  counter_analyze: "checking the conclusion",
  completed: "finished",
};

export function phaseLabel(step: string | null | undefined): string {
  if (!step) return "starting";
  return PHASE_LABEL[step] ?? step.replace(/_/g, " ");
}

const ENDED: Record<string, { tone: PillTone; label: string }> = {
  completed: { tone: "ok", label: "finished" },
  failed: { tone: "bad", label: "failed" },
  cancelled: { tone: "neutral", label: "cancelled" },
  terminated: { tone: "neutral", label: "stopped" },
  timed_out: { tone: "bad", label: "timed out" },
};

const BRIEF_ITEM_MAX = 80;

function clipped(text: string): string {
  return text.length > BRIEF_ITEM_MAX
    ? `${text.slice(0, BRIEF_ITEM_MAX - 1)}…`
    : text;
}

/**
 * The brief in one line, as the mockup writes it: "Brief: completed orders
 * −30% on 09-14 · only app_v2 · ruled out: region · lead: app_v2 deploy".
 */
export function briefLine(brief: InvestigationBrief): string {
  const parts = [brief.symptom];
  for (const finding of brief.findings ?? []) {
    parts.push(clipped(finding.statement));
  }
  const ruledOut = (brief.ruled_out ?? []).map((c) => clipped(c.statement));
  if (ruledOut.length > 0) parts.push(`ruled out: ${ruledOut.join(", ")}`);
  const leads = (brief.leads ?? []).filter(Boolean).map(clipped);
  if (leads.length > 0) {
    parts.push(`${leads.length === 1 ? "lead" : "leads"}: ${leads.join(", ")}`);
  }
  return parts.join(" · ");
}

export function BriefSummary({ brief }: { brief: InvestigationBrief }) {
  const sections: [string, string[]][] = [
    ["Findings", (brief.findings ?? []).map((c) => c.statement)],
    ["Ruled out", (brief.ruled_out ?? []).map((c) => c.statement)],
    ["Leads", brief.leads ?? []],
    ["Tables", brief.scope?.tables ?? []],
  ];
  return (
    <div className="mt-1.5 space-y-1.5 rounded-md bg-muted/50 px-3 py-2 text-xs">
      <p>
        <span className="font-semibold">Symptom:</span> {brief.symptom}
      </p>
      {sections
        .filter(([, items]) => items.length > 0)
        .map(([title, items]) => (
          <div key={title}>
            <p className="font-semibold">{title}</p>
            <ul className="ml-4 list-disc">
              {items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      {brief.scope?.time_window && (
        <p>
          <span className="font-semibold">Time window:</span>{" "}
          {brief.scope.time_window.from} → {brief.scope.time_window.to}
        </p>
      )}
      {brief.notes && (
        <p>
          <span className="font-semibold">Notes:</span> {brief.notes}
        </p>
      )}
    </div>
  );
}

export interface InvestigationCardProps {
  message: ThreadMessage;
  /** The outcome the run posted, once it finished. */
  outcome?: InvestigationOutcome | null;
  /** The issue's record of this run, once the runs list has loaded. */
  run?: InvestigationRunResponse;
  /** The run's number among the issue's runs. */
  number?: number;
  canWrite: boolean;
  nameOf: (userId: string | null | undefined) => string;
}

export function InvestigationCard({
  message,
  outcome,
  run,
  number,
  canWrite,
  nameOf,
}: InvestigationCardProps) {
  const payload = message.payload as InvestigationPayload;
  const investigationId = payload.investigation_id ?? null;
  const brief = asBrief(payload.brief);
  const hub = useIssueHub();
  const [showBrief, setShowBrief] = useState(false);
  const live = useLiveStatus(investigationId);
  const status = live.data;
  const failedOutcome = isFailedOutcome(outcome);
  const running = !failedOutcome && isRunning(status);
  const steers = useSteers(investigationId, running);
  const failed =
    failedOutcome ||
    (!running &&
      (status?.workflow_status === "failed" ||
        (!!run && runStatus(run) === "failed")));
  const failure = failed
    ? (outcome?.error?.message ?? run?.error ?? null)
    : null;

  // A finished run's status has no hypotheses; its outcome does.
  const hypotheses: HypothesisState[] =
    (running ? status?.hypotheses : null) ??
    outcome?.hypotheses ??
    status?.hypotheses ??
    [];

  let pill: { tone: PillTone; label: string };
  if (running) {
    pill = {
      tone: "agent",
      label: `running · ${phaseLabel(status?.current_step)}`,
    };
  } else if (failed) {
    pill = ENDED.failed;
  } else if (status) {
    pill = ENDED[status.workflow_status] ?? {
      tone: "neutral",
      label: status.workflow_status,
    };
  } else if (outcome) {
    pill = ENDED.completed;
  } else if (live.isError) {
    pill = { tone: "neutral", label: "status unavailable" };
  } else {
    pill = { tone: "neutral", label: "loading…" };
  }

  const progress =
    running && typeof status?.progress === "number"
      ? Math.round(Math.min(Math.max(status.progress, 0), 1) * 100)
      : null;
  const fromScratch =
    !!payload.source_thread_id &&
    payload.source_thread_id !== message.thread_id;
  // A failed outcome in the thread carries its own Retry.
  const canRetry = failed && !failedOutcome && canWrite && !!hub && !!brief;

  return (
    <div
      className="mt-2 rounded-[10px] border border-border px-3 py-2.5"
      aria-label="Investigation"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13.5px] font-semibold">
          {number
            ? `Investigation #${number}`
            : payload.parent_run_id
              ? "Follow-up investigation"
              : "Investigation"}
        </h4>
        <Pill tone={pill.tone}>{pill.label}</Pill>
        {payload.execution_profile && <Pill>{payload.execution_profile}</Pill>}
        {fromScratch && <Pill tone="info">from a scratch chat</Pill>}
        {investigationId && (
          <Link
            to={`/investigations/${investigationId}`}
            className={`ml-auto text-xs ${LINK_CLASS}`}
          >
            details →
          </Link>
        )}
      </div>

      {brief && (
        <div className="mt-1 text-[12.5px] text-muted-foreground">
          Brief: {briefLine(brief)}.{" "}
          <button
            type="button"
            className={LINK_CLASS}
            aria-expanded={showBrief}
            onClick={() => setShowBrief((s) => !s)}
          >
            {showBrief ? "hide brief" : "view brief"}
          </button>
          {showBrief && <BriefSummary brief={brief} />}
        </div>
      )}

      {failed && (
        <div className="mt-2 space-y-2">
          <p className="text-sm text-red-700 dark:text-red-400">
            {failure ?? "The run failed before it could finish."}
          </p>
          {canRetry && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              onClick={() =>
                hub.openBriefEditor({
                  kind: "brief",
                  brief: brief!,
                  sourceThreadId: payload.source_thread_id ?? message.thread_id,
                })
              }
            >
              <RotateCcw className="h-3 w-3" />
              Retry
            </Button>
          )}
        </div>
      )}

      {progress !== null && (
        <div
          className="my-2 h-1.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Investigation progress"
        >
          <div
            className="h-full bg-violet-600 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {investigationId && (
        <Steering
          investigationId={investigationId}
          running={running}
          hypotheses={hypotheses}
          steers={steers.data?.items ?? []}
          canWrite={canWrite}
          nameOf={nameOf}
        />
      )}
      {running && hypotheses.length === 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Hypotheses appear here once the manager has generated them.
        </p>
      )}
    </div>
  );
}
