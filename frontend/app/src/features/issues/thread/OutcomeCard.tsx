/**
 * The outcome a finished investigation posts to the thread: the root cause,
 * how each hypothesis ended, and the review actions (spec 0001 §7.10). A run
 * that failed posts why instead, with Retry (§7.12).
 */

import { useState } from "react";
import { Check, FlaskConical, Loader2, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { CodifyModal } from "@/features/investigation/components/codify-widget";
import { errorText } from "@/lib/api/error-message";
import {
  asBrief,
  isFailedOutcome,
  useReviewOutcome,
  type InvestigationBrief,
  type InvestigationOutcome,
} from "@/lib/api/investigation-runs";
import type { InvestigationRunResponse } from "@/lib/api/issues";
import type { ThreadMessage } from "@/lib/api/issue-threads";

import { continuationBrief } from "../brief/brief-form";
import { useIssueHub } from "../hub/hub-context";
import { phaseLabel } from "./InvestigationCard";
import { Pill, hypothesisStatus, type PillTone } from "./Pill";

/** Codify refuses a synthesis below this confidence. */
const CODIFY_MIN_CONFIDENCE = 0.6;

interface OutcomePayload {
  investigation_id?: string;
  run_id?: string | null;
  outcome?: InvestigationOutcome;
}

function confidenceTone(confidence: number): PillTone {
  if (confidence >= 0.8) return "ok";
  if (confidence >= 0.5) return "warn";
  return "bad";
}

function evidenceText(item: unknown): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>;
    for (const key of ["description", "summary", "statement", "finding"]) {
      if (typeof record[key] === "string") return record[key] as string;
    }
    return JSON.stringify(item);
  }
  return String(item);
}

/** Why the conclusion's check (counter-analysis) didn't run, if it didn't. */
function counterAnalysisError(outcome: InvestigationOutcome): string | null {
  const counter = outcome.counter_analysis as { error?: unknown } | null;
  return counter && typeof counter.error === "string" && counter.error
    ? counter.error
    : null;
}

interface OutcomeCardProps {
  message: ThreadMessage;
  issueId: string;
  /** The issue's record of this run, once the runs list has loaded. */
  run?: InvestigationRunResponse;
  /** The run's number among the issue's runs. */
  number?: number;
  /** The brief the run started with, for Retry. */
  brief?: InvestigationBrief | null;
  canWrite: boolean;
  nameOf: (userId: string | null | undefined) => string;
}

/** A run that failed: the reason, and Retry with the same brief. */
function FailedOutcome({
  message,
  outcome,
  run,
  number,
  brief,
  canWrite,
}: {
  message: ThreadMessage;
  outcome: InvestigationOutcome;
  run?: InvestigationRunResponse;
  number?: number;
  brief?: InvestigationBrief | null;
  canWrite: boolean;
}) {
  const hub = useIssueHub();
  const error = outcome.error ?? null;
  const retry = () => {
    if (!hub) return;
    hub.openBriefEditor({
      kind: "brief",
      brief: brief ?? asBrief(run?.brief) ?? { symptom: hub.issueTitle },
      sourceThreadId: run?.source_thread_id ?? message.thread_id,
    });
  };

  return (
    <div
      className="mt-2 rounded-[10px] border border-border px-3 py-2.5"
      aria-label="Investigation outcome"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13.5px] font-semibold">
          {number ? `Investigation #${number}` : "Investigation"}
        </h4>
        <Pill tone="bad">failed</Pill>
        {error?.step && (
          <span className="text-xs text-muted-foreground">
            while {phaseLabel(error.step)}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-red-700 dark:text-red-400">
        {error?.message ||
          run?.error ||
          "The run failed before it could finish."}
      </p>
      {canWrite && hub && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Button size="sm" className="h-7 gap-1 text-xs" onClick={retry}>
            <RotateCcw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}

export function OutcomeCard(props: OutcomeCardProps) {
  const outcome = (props.message.payload as OutcomePayload).outcome ?? {};
  if (isFailedOutcome(outcome)) {
    return (
      <FailedOutcome
        message={props.message}
        outcome={outcome}
        run={props.run}
        number={props.number}
        brief={props.brief}
        canWrite={props.canWrite}
      />
    );
  }
  return <RootCauseOutcome {...props} />;
}

function RootCauseOutcome({
  message,
  issueId,
  run,
  canWrite,
  nameOf,
}: OutcomeCardProps) {
  const payload = message.payload as OutcomePayload;
  const outcome = payload.outcome ?? {};
  const investigationId = payload.investigation_id ?? null;
  const hub = useIssueHub();
  const review = useReviewOutcome(issueId);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [codifyOpen, setCodifyOpen] = useState(false);

  const rootCause = outcome.root_cause || null;
  const confidence =
    typeof outcome.confidence === "number" ? outcome.confidence : null;
  const verdict = run?.outcome_verdict ?? null;
  const hypotheses = outcome.hypotheses ?? [];
  const evidence = outcome.supporting_evidence ?? [];
  const recommendations = outcome.recommendations ?? [];
  const checkError = counterAnalysisError(outcome);

  const send = async (next: "confirmed" | "rejected") => {
    if (!investigationId) return;
    const note = next === "rejected" ? reason.trim() : null;
    if (next === "rejected" && !note) return;
    try {
      await review.mutateAsync({ investigationId, verdict: next, note });
      if (next === "confirmed") {
        toast.success("Root cause confirmed", {
          description:
            "Resolving the issue pre-fills its note with this cause.",
        });
      } else {
        toast.success("Outcome rejected", {
          description: "Continue investigating to start a follow-up run.",
        });
        setRejecting(false);
        setReason("");
      }
    } catch (error) {
      toast.error(
        next === "confirmed"
          ? "Couldn't confirm the outcome"
          : "Couldn't reject the outcome",
        { description: errorText(error) },
      );
    }
  };

  const continueInvestigating = () => {
    if (!hub) return;
    const prior = asBrief(run?.brief) ?? { symptom: hub.issueTitle };
    hub.openBriefEditor({
      kind: "brief",
      brief: continuationBrief(
        prior,
        rootCause ?? run?.synthesis_summary,
        verdict === "rejected" ? { note: run?.outcome_note } : null,
      ),
      sourceThreadId: message.thread_id,
      parentRunId: run?.id ?? payload.run_id ?? null,
    });
  };

  const canCodify = confidence !== null && confidence >= CODIFY_MIN_CONFIDENCE;

  return (
    <div
      className="mt-2 rounded-[10px] border border-border px-3 py-2.5"
      aria-label="Investigation outcome"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13.5px] font-semibold">Root cause</h4>
        {confidence !== null && (
          <Pill tone={confidenceTone(confidence)}>
            confidence {confidence.toFixed(2)}
          </Pill>
        )}
        {verdict === "confirmed" && <Pill tone="ok">confirmed</Pill>}
        {verdict === "rejected" && <Pill tone="bad">rejected</Pill>}
      </div>
      <p className="mt-1 text-sm">
        {rootCause ?? "The investigation didn't establish a root cause."}
      </p>

      {hypotheses.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {hypotheses.map((h, i) => {
            const status = hypothesisStatus(h.status);
            return (
              <Pill key={h.id} tone={status.tone}>
                <span title={h.title}>
                  H{i + 1} {status.label}
                </span>
              </Pill>
            );
          })}
        </div>
      )}
      {hypotheses.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
          {hypotheses.map((h, i) => (
            <li key={h.id}>
              H{i + 1} · {h.title || h.id}
            </li>
          ))}
        </ul>
      )}

      {evidence.length > 0 && (
        <div className="mt-2 text-xs">
          <p className="font-semibold">Supporting evidence</p>
          <ul className="ml-4 list-disc text-muted-foreground">
            {evidence.map((item, i) => (
              <li key={i}>{evidenceText(item)}</li>
            ))}
          </ul>
        </div>
      )}
      {recommendations.length > 0 && (
        <div className="mt-2 text-xs">
          <p className="font-semibold">Recommendations</p>
          <ul className="ml-4 list-disc text-muted-foreground">
            {recommendations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {checkError && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
          The check of this conclusion didn't run: {checkError}
        </p>
      )}

      {run?.outcome_verdict && (
        <p
          className={
            verdict === "confirmed"
              ? "mt-2 text-xs text-green-700 dark:text-green-400"
              : "mt-2 text-xs text-red-700 dark:text-red-400"
          }
        >
          {verdict === "confirmed" ? "Confirmed" : "Rejected"} by{" "}
          {nameOf(run.outcome_reviewed_by)}
          {run.outcome_note ? `: ${run.outcome_note}` : ""}
        </p>
      )}

      {canWrite && investigationId && (
        <>
          {rejecting ? (
            <div className="mt-2 space-y-2">
              <label
                htmlFor={`reject-${message.id}`}
                className="block text-xs font-semibold text-muted-foreground"
              >
                Why is this wrong?
              </label>
              <Textarea
                id={`reject-${message.id}`}
                value={reason}
                rows={2}
                maxLength={2000}
                onChange={(e) => setReason(e.target.value)}
                placeholder="What the investigation missed or got wrong"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-7 text-xs"
                  disabled={!reason.trim() || review.isPending}
                  onClick={() => void send("rejected")}
                >
                  Reject outcome
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs"
                  onClick={() => setRejecting(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Button
                size="sm"
                className="h-7 gap-1 text-xs"
                disabled={review.isPending || verdict === "confirmed"}
                onClick={() => void send("confirmed")}
              >
                {review.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                Confirm
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                disabled={review.isPending || verdict === "rejected"}
                onClick={() => setRejecting(true)}
              >
                <X className="h-3 w-3" />
                Reject
              </Button>
              {hub && (
                <Button
                  size="sm"
                  variant={verdict === "rejected" ? "default" : "outline"}
                  className="h-7 gap-1 text-xs"
                  onClick={continueInvestigating}
                >
                  <RotateCcw className="h-3 w-3" />
                  Continue investigating
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                disabled={!canCodify}
                title={
                  canCodify
                    ? undefined
                    : "Checks need a root cause with confidence of at least 0.6"
                }
                onClick={() => setCodifyOpen(true)}
              >
                <FlaskConical className="h-3 w-3" />
                Add as check
              </Button>
            </div>
          )}
          {codifyOpen && (
            <CodifyModal
              isOpen={codifyOpen}
              onClose={() => setCodifyOpen(false)}
              investigationId={investigationId}
            />
          )}
        </>
      )}
    </div>
  );
}
