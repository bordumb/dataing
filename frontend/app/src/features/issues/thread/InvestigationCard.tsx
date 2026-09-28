/**
 * The card for an investigation started from the issue: its brief, live
 * phase and the manager's hypotheses as its subagents test them.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import {
  asBrief,
  isRunning,
  useLiveStatus,
  type HypothesisState,
  type InvestigationBrief,
  type InvestigationOutcome,
} from "@/lib/api/investigation-runs";
import type { ThreadMessage } from "@/lib/api/issue-threads";

import { Pill, hypothesisStatus, type PillTone } from "./Pill";

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

export interface HypothesisRowProps {
  hypothesis: HypothesisState;
  index: number;
  /** Extra words after the status, e.g. who ruled it out. */
  note?: string;
  action?: React.ReactNode;
}

export function HypothesisRow({
  hypothesis,
  index,
  note,
  action,
}: HypothesisRowProps) {
  const status = hypothesisStatus(hypothesis.status);
  return (
    <li
      className="flex items-center gap-2 border-t border-border py-1.5 text-sm"
      aria-label={`Hypothesis ${hypothesis.title}`}
    >
      <Pill tone={status.tone}>{status.label}</Pill>
      <span
        className={
          hypothesis.status === "ruled_out"
            ? "flex-1 text-muted-foreground line-through"
            : "flex-1"
        }
      >
        H{index + 1} · {hypothesis.title || hypothesis.id}
      </span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
      {action}
    </li>
  );
}

export interface InvestigationCardProps {
  message: ThreadMessage;
  /** The outcome the run posted, once it finished. */
  outcome?: InvestigationOutcome | null;
}

export function InvestigationCard({
  message,
  outcome,
}: InvestigationCardProps) {
  const payload = message.payload as InvestigationPayload;
  const investigationId = payload.investigation_id ?? null;
  const brief = asBrief(payload.brief);
  const [showBrief, setShowBrief] = useState(false);
  const live = useLiveStatus(investigationId);
  const status = live.data;
  const running = isRunning(status);

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

  return (
    <div
      className="mt-1 rounded-lg border border-border px-3 py-2.5"
      aria-label="Investigation"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">
          {payload.parent_run_id ? "Follow-up investigation" : "Investigation"}
        </h4>
        <Pill tone={pill.tone}>{pill.label}</Pill>
        {payload.execution_profile && <Pill>{payload.execution_profile}</Pill>}
        {fromScratch && <Pill tone="info">from a scratch chat</Pill>}
        {investigationId && (
          <Link
            to={`/investigations/${investigationId}`}
            className="ml-auto inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Open
            <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </div>

      {brief && (
        <div className="mt-1 text-xs text-muted-foreground">
          Brief: {brief.symptom}
          {(brief.findings?.length ?? 0) > 0 &&
            ` · ${brief.findings!.length} finding${brief.findings!.length === 1 ? "" : "s"}`}
          {(brief.ruled_out?.length ?? 0) > 0 &&
            ` · ${brief.ruled_out!.length} ruled out`}
          {(brief.leads?.length ?? 0) > 0 &&
            ` · ${brief.leads!.length} lead${brief.leads!.length === 1 ? "" : "s"}`}
          .{" "}
          <button
            type="button"
            className="text-primary hover:underline"
            aria-expanded={showBrief}
            onClick={() => setShowBrief((s) => !s)}
          >
            {showBrief ? "hide brief" : "view brief"}
          </button>
          {showBrief && <BriefSummary brief={brief} />}
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

      {hypotheses.length > 0 ? (
        <ul className="mt-2">
          {hypotheses.map((h, i) => (
            <HypothesisRow key={h.id} hypothesis={h} index={i} />
          ))}
        </ul>
      ) : (
        running && (
          <p className="mt-2 text-xs text-muted-foreground">
            Hypotheses appear here once the manager has generated them.
          </p>
        )
      )}
    </div>
  );
}
