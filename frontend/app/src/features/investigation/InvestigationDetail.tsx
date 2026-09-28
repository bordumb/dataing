/**
 * A run's details page (spec 0001 D14, §8.3). The thread's card is the main
 * view of a run; this page keeps what the card has no room for: the brief,
 * every hypothesis with its evidence and queries, the full outcome, share,
 * snapshot export and Add as check. A failed run says why, and what to do.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Download, Link2, Loader2, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { errorText } from "@/lib/api/error-message";
import { useCancelInvestigationApiV1InvestigationsInvestigationIdCancelPost } from "@/lib/api/generated/investigations/investigations";
import type {
  InvestigationBrief,
  RunError,
} from "@/lib/api/investigation-runs";
import {
  fetchSnapshot,
  hasEnded,
  subscribeToInvestigation,
  useInvestigation,
  type InvestigationState,
  type RunHypothesis,
} from "@/lib/api/investigations";
import { useRole } from "@/lib/auth";

import { phaseLabel } from "@/features/issues/thread/InvestigationCard";
import { LINK_CLASS } from "@/features/issues/thread/message-parts";
import {
  Pill,
  hypothesisStatus,
  type PillTone,
} from "@/features/issues/thread/Pill";
import {
  CodifyWidget,
  PatternList,
  SupportBadge,
  evidenceFields,
} from "./components";
import { InvestigationFeedbackButtons } from "./components/InvestigationFeedbackButtons";
import { InvestigationFeedbackProvider } from "./context/InvestigationFeedbackContext";

// ----------------------------------------------------------------------------
// Status
// ----------------------------------------------------------------------------

const ENDED: Record<string, { tone: PillTone; label: string }> = {
  completed: { tone: "ok", label: "finished" },
  inconclusive: { tone: "warn", label: "inconclusive" },
  failed: { tone: "bad", label: "failed" },
  cancelled: { tone: "neutral", label: "cancelled" },
  terminated: { tone: "neutral", label: "stopped" },
  timed_out: { tone: "bad", label: "timed out" },
};

function statusPill(state: InvestigationState): {
  tone: PillTone;
  label: string;
} {
  if (state.error) return ENDED.failed;
  if (!hasEnded(state)) {
    return {
      tone: "agent",
      label: `running · ${phaseLabel(state.main_branch.current_step)}`,
    };
  }
  return ENDED[state.status] ?? { tone: "neutral", label: state.status };
}

/** What to do about a failure, beyond what its message already says. */
function nextStep(error: RunError): string {
  switch (error.code) {
    case "missing_key":
    case "invalid_key":
    case "forbidden":
    case "unknown_model":
      return "Once it's fixed, retry from the issue: Retry on the run's card starts a new run with the same brief.";
    case "rate_limited":
    case "overloaded":
    case "server_error":
    case "unreachable":
      return "This is usually temporary. Retry from the issue in a few minutes.";
    default:
      return "Retry from the issue. If it fails the same way, check the worker's logs.";
  }
}

// ----------------------------------------------------------------------------
// Header
// ----------------------------------------------------------------------------

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function ShareButton() {
  const location = useLocation();
  const share = async () => {
    const url = new URL(
      `${location.pathname}${location.search}`,
      window.location.origin,
    ).href;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Couldn't copy the link", { description: url });
    }
  };
  return (
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5"
      onClick={() => void share()}
    >
      <Link2 className="h-4 w-4" />
      Share
    </Button>
  );
}

function ExportSnapshotButton({
  investigationId,
}: {
  investigationId: string;
}) {
  const [pending, setPending] = useState(false);
  const exportSnapshot = async () => {
    setPending(true);
    try {
      saveBlob(
        await fetchSnapshot(investigationId),
        `snapshot-${investigationId}.tar.gz`,
      );
    } catch (error) {
      toast.error("Couldn't export the snapshot", {
        description: errorText(error),
      });
    } finally {
      setPending(false);
    }
  };
  return (
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5"
      disabled={pending}
      onClick={() => void exportSnapshot()}
    >
      {pending ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Download className="h-4 w-4" />
      )}
      Export snapshot
    </Button>
  );
}

function RunHeader({
  state,
  live,
  onCancel,
  cancelling,
}: {
  state: InvestigationState;
  live: boolean;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const { isMember } = useRole();
  const pill = statusPill(state);
  const ended = hasEnded(state);
  const synthesis = state.main_branch.synthesis as {
    confidence?: unknown;
  } | null;
  const confidence =
    typeof synthesis?.confidence === "number" ? synthesis.confidence : 0;

  return (
    <header className="space-y-2">
      {state.issue_id && (
        <Link
          to={`/issues/${state.issue_id}`}
          className={`inline-block text-sm ${LINK_CLASS}`}
        >
          ← {state.issue_number ? `#${state.issue_number} ` : ""}
          {state.issue_title ?? "Back to the issue"}
        </Link>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-xl font-semibold">
          {state.run_number
            ? `Investigation #${state.run_number}`
            : "Investigation"}
        </h1>
        <Pill tone={pill.tone}>{pill.label}</Pill>
        {state.execution_profile && <Pill>{state.execution_profile}</Pill>}
        {live && !ended && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
            live
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <ShareButton />
          <ExportSnapshotButton investigationId={state.investigation_id} />
          {isMember && ended && !state.error && state.main_branch.synthesis && (
            <CodifyWidget
              investigationId={state.investigation_id}
              confidence={confidence}
              isComplete={ended}
            />
          )}
          {isMember && !ended && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-destructive hover:text-destructive"
              onClick={onCancel}
              disabled={cancelling}
            >
              {cancelling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Cancel run
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}

// ----------------------------------------------------------------------------
// Sections
// ----------------------------------------------------------------------------

const PANEL = "rounded-[10px] border border-border bg-card px-4 py-3";

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h2>
  );
}

function BriefList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="font-medium">{title}</p>
      <ul className="ml-5 list-disc text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function BriefSection({ brief }: { brief: InvestigationBrief }) {
  const window_ = brief.scope?.time_window;
  return (
    <section aria-label="Brief" className={PANEL}>
      <SectionHeading>Brief</SectionHeading>
      <div className="space-y-2 text-sm">
        <p>{brief.symptom}</p>
        <BriefList
          title="Findings"
          items={(brief.findings ?? []).map((c) => c.statement)}
        />
        <BriefList
          title="Ruled out"
          items={(brief.ruled_out ?? []).map((c) => c.statement)}
        />
        <BriefList title="Leads" items={brief.leads ?? []} />
        {(brief.scope?.tables ?? []).length > 0 && (
          <div>
            <p className="font-medium">Tables</p>
            <p className="flex flex-wrap gap-1.5">
              {brief.scope!.tables!.map((table) => (
                <code
                  key={table}
                  className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs"
                >
                  {table}
                </code>
              ))}
            </p>
          </div>
        )}
        {window_ && (
          <p>
            <span className="font-medium">Time window:</span>{" "}
            <span className="text-muted-foreground">
              {window_.from} → {window_.to}
            </span>
          </p>
        )}
        {brief.notes && (
          <p>
            <span className="font-medium">Notes:</span>{" "}
            <span className="text-muted-foreground">{brief.notes}</span>
          </p>
        )}
      </div>
    </section>
  );
}

/** One query the subagent ran: its SQL, the result summary and what it means. */
function EvidenceQuery({
  evidence,
  index,
}: {
  evidence: Record<string, unknown>;
  index: number;
}) {
  const fields = evidenceFields(evidence, index);
  return (
    <div>
      {fields.query && (
        <pre className="whitespace-pre-wrap border-b border-border px-3 py-2 font-mono text-xs">
          {fields.query}
        </pre>
      )}
      {fields.resultSummary && (
        <div className="border-b border-border px-3 py-2">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Result
          </p>
          <pre className="whitespace-pre-wrap font-mono text-xs">
            {fields.resultSummary}
          </pre>
        </div>
      )}
      <div className="flex flex-wrap items-start gap-2 px-3 py-2 text-sm">
        <SupportBadge supports={fields.supports} />
        {fields.confidence > 0 && (
          <Pill>confidence {fields.confidence.toFixed(2)}</Pill>
        )}
        <p className="min-w-0 flex-1">{fields.interpretation}</p>
        <InvestigationFeedbackButtons
          targetType="evidence"
          targetId={`${fields.hypothesisId}-${index}`}
        />
      </div>
    </div>
  );
}

function plural(n: number, word: string, many = `${word}s`) {
  return `${n.toLocaleString("en-US")} ${n === 1 ? word : many}`;
}

/** A hypothesis's queries, collapsed to one line like the thread's tool calls. */
function EvidenceQueries({ items }: { items: Record<string, unknown>[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  const rows = items.reduce(
    (sum, item, i) => sum + evidenceFields(item, i).rowCount,
    0,
  );
  return (
    <div className="mt-1.5 overflow-hidden rounded-lg border border-border">
      <button
        type="button"
        className="flex w-full items-center gap-1.5 bg-muted px-2.5 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>{" "}
        {`Ran ${plural(items.length, "query", "queries")} · ${plural(rows, "row")}`}
      </button>
      {open && (
        <div className="divide-y divide-border">
          {items.map((item, i) => (
            <EvidenceQuery key={i} evidence={item} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

/** The run's hypotheses; runs recorded without them are grouped by evidence. */
function hypothesesOf(state: InvestigationState): RunHypothesis[] {
  if (state.hypotheses && state.hypotheses.length > 0) return state.hypotheses;
  const ids = new Set<string>();
  state.main_branch.evidence.forEach((item, i) =>
    ids.add(evidenceFields(item, i).hypothesisId),
  );
  return [...ids].map((id) => ({
    id,
    title: id,
    status: "",
    reasoning: null,
  }));
}

function HypothesesSection({ state }: { state: InvestigationState }) {
  const hypotheses = hypothesesOf(state);
  const evidence = state.main_branch.evidence;
  const byHypothesis = (id: string) =>
    evidence.filter((item, i) => evidenceFields(item, i).hypothesisId === id);
  const known = new Set(hypotheses.map((h) => h.id));
  const other = evidence.filter(
    (item, i) => !known.has(evidenceFields(item, i).hypothesisId),
  );

  return (
    <section aria-label="Hypotheses" className={PANEL}>
      <SectionHeading>Hypotheses</SectionHeading>
      {hypotheses.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {hasEnded(state)
            ? "The run tested no hypotheses."
            : "Hypotheses appear here once the manager has generated them."}
        </p>
      ) : (
        <ul>
          {hypotheses.map((h, i) => {
            const status = h.status ? hypothesisStatus(h.status) : null;
            return (
              <li
                key={h.id}
                aria-label={`Hypothesis ${h.title}`}
                className="border-t border-border py-2 first:border-t-0 first:pt-0"
              >
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  {status && <Pill tone={status.tone}>{status.label}</Pill>}
                  <span
                    className={
                      h.status === "ruled_out"
                        ? "flex-1 text-muted-foreground line-through"
                        : "flex-1"
                    }
                  >
                    H{i + 1} · {h.title || h.id}
                  </span>
                  <InvestigationFeedbackButtons
                    targetType="hypothesis"
                    targetId={h.id}
                  />
                </div>
                {h.reasoning && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {h.reasoning}
                  </p>
                )}
                <EvidenceQueries items={byHypothesis(h.id)} />
              </li>
            );
          })}
        </ul>
      )}
      {other.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-medium text-muted-foreground">
            Other evidence
          </p>
          <EvidenceQueries items={other} />
        </div>
      )}
    </section>
  );
}

interface Synthesis {
  confidence?: number;
  root_cause?: string | null;
  summary?: string;
  recommendations?: string[];
  supporting_evidence?: string[];
  causal_chain?: string[];
  estimated_onset?: string;
  affected_scope?: string;
}

function confidenceTone(confidence: number): PillTone {
  if (confidence >= 0.8) return "ok";
  if (confidence >= 0.5) return "warn";
  return "bad";
}

/** The conclusion, in the thread's outcome-card style. */
function OutcomeSection({
  state,
  investigationId,
}: {
  state: InvestigationState;
  investigationId: string;
}) {
  const raw = state.main_branch.synthesis;
  const syn: Synthesis =
    raw && typeof raw === "object" ? (raw as Synthesis) : {};
  const cause =
    (typeof syn.root_cause === "string" && syn.root_cause) ||
    (typeof syn.summary === "string" && syn.summary) ||
    (typeof raw === "string" ? raw : null);
  const confidence = typeof syn.confidence === "number" ? syn.confidence : null;
  const chain = Array.isArray(syn.causal_chain) ? syn.causal_chain : [];
  const recommendations = Array.isArray(syn.recommendations)
    ? syn.recommendations
    : [];
  const supporting = Array.isArray(syn.supporting_evidence)
    ? syn.supporting_evidence
    : [];
  const hypotheses = state.hypotheses ?? [];

  return (
    <section aria-label="Outcome" className={PANEL}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Root cause</h2>
        {confidence !== null && (
          <Pill tone={confidenceTone(confidence)}>
            confidence {confidence.toFixed(2)}
          </Pill>
        )}
        <span className="ml-auto">
          <InvestigationFeedbackButtons
            targetType="synthesis"
            targetId={investigationId}
          />
        </span>
      </div>
      <p className="mt-1 text-sm">
        {cause ?? "The investigation didn't establish a root cause."}
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

      {chain.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Causal chain
          </p>
          <ol className="flex flex-wrap items-center gap-1.5 text-sm">
            {chain.map((step, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <span className="rounded border border-border px-2 py-0.5">
                  {step}
                </span>
                {i < chain.length - 1 && (
                  <span aria-hidden className="text-muted-foreground">
                    →
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {(syn.estimated_onset || syn.affected_scope) && (
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          {syn.estimated_onset && (
            <div>
              <dt className="text-xs font-medium text-muted-foreground">
                Onset
              </dt>
              <dd>{syn.estimated_onset}</dd>
            </div>
          )}
          {syn.affected_scope && (
            <div>
              <dt className="text-xs font-medium text-muted-foreground">
                Affected scope
              </dt>
              <dd>{syn.affected_scope}</dd>
            </div>
          )}
        </dl>
      )}

      {recommendations.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Recommendations
          </p>
          <ul className="space-y-1 text-sm">
            {recommendations.map((rec, i) => (
              <li key={i} className="flex items-start justify-between gap-2">
                <span className="flex gap-2">
                  <span aria-hidden>•</span>
                  {rec}
                </span>
                <InvestigationFeedbackButtons
                  targetType="recommendation"
                  targetId={`${investigationId}-rec-${i}`}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {supporting.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Supporting evidence
          </p>
          <ul className="ml-5 list-disc text-sm text-muted-foreground">
            {supporting.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** A failed run: why, and what to do, in place of a conclusion. */
function FailureSection({
  error,
  issueId,
}: {
  error: RunError;
  issueId: string | null | undefined;
}) {
  return (
    <section aria-label="Outcome" className={PANEL}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">The run failed</h2>
        <Pill tone="bad">failed</Pill>
        {error.step && (
          <span className="text-xs text-muted-foreground">
            while {phaseLabel(error.step)}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-red-700 dark:text-red-400">
        {error.message}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">{nextStep(error)}</p>
      {issueId && (
        <Link
          to={`/issues/${issueId}`}
          className={`mt-2 inline-block text-sm ${LINK_CLASS}`}
        >
          Retry from the issue →
        </Link>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------
// Page
// ----------------------------------------------------------------------------

function RunDetails({
  state,
  refetch,
}: {
  state: InvestigationState;
  refetch: () => unknown;
}) {
  const id = state.investigation_id;
  const cancel =
    useCancelInvestigationApiV1InvestigationsInvestigationIdCancelPost();
  const ended = hasEnded(state);
  const [live, setLive] = useState(false);

  // Follow a running run over SSE; polling covers a dropped stream.
  useEffect(() => {
    if (ended) return;
    const cleanup = subscribeToInvestigation(id, {
      onStepChanged: () => void refetch(),
      onStatusChanged: () => void refetch(),
      onEnded: () => void refetch(),
      onError: () => setLive(false),
    });
    setLive(true);
    return () => {
      cleanup();
      setLive(false);
    };
  }, [id, ended, refetch]);

  const onCancel = async () => {
    if (!window.confirm("Cancel this run? It stops where it is.")) return;
    try {
      await cancel.mutateAsync({ investigationId: id });
      void refetch();
    } catch (error) {
      toast.error("Couldn't cancel the run", { description: errorText(error) });
    }
  };

  const failure: RunError | null =
    state.error ??
    (state.status === "failed"
      ? {
          code: "failed",
          message: "The run failed before it could finish.",
        }
      : null);
  const patterns = state.main_branch.matched_patterns ?? [];
  const stopped =
    (state.status === "cancelled" || state.status === "terminated") &&
    !state.main_branch.synthesis;

  return (
    <InvestigationFeedbackProvider investigationId={id}>
      <div className="mx-auto max-w-[1000px] space-y-4">
        <RunHeader
          state={state}
          live={live}
          onCancel={() => void onCancel()}
          cancelling={cancel.isPending}
        />
        {state.brief && <BriefSection brief={state.brief} />}
        {patterns.length > 0 && (
          <div className={PANEL}>
            <PatternList patterns={patterns} />
          </div>
        )}
        <HypothesesSection state={state} />
        {failure ? (
          <FailureSection error={failure} issueId={state.issue_id} />
        ) : stopped ? (
          <section aria-label="Outcome" className={PANEL}>
            <p className="text-sm text-muted-foreground">
              The run was stopped before it reached a conclusion.
            </p>
          </section>
        ) : ended ? (
          <OutcomeSection state={state} investigationId={id} />
        ) : null}
      </div>
    </InvestigationFeedbackProvider>
  );
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error, refetch } = useInvestigation(id);

  if (!id) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">Investigation ID not provided</p>
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load investigation: {error?.message || "Not found"}
          </p>
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return <RunDetails state={data} refetch={refetch} />;
}
