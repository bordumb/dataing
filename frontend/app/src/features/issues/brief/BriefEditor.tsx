/**
 * The brief editor: what a thread hands to the investigation manager and its
 * subagents (spec 0001 §7.7). The agent drafts the brief from the thread; the
 * person edits it, picks the depth and datasource, and starts the run.
 *
 * BriefFormView is shared with "Start an investigation" (StartInvestigation),
 * the same editor in new mode.
 */

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Plus, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { DatePicker } from "@/components/ui/DatePicker";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/textarea";
import { DatasetEntry } from "@/features/investigation/components";
import { useDataSources } from "@/lib/api/datasources";
import { errorText } from "@/lib/api/error-message";
import {
  asBrief,
  useStartRun,
  type ExecutionProfile,
  type InvestigationBrief,
} from "@/lib/api/investigation-runs";
import { useThreadMessages, type ThreadMessage } from "@/lib/api/issue-threads";
import { queryKeys } from "@/lib/api/query-keys";
import { cn } from "@/lib/utils";

import type { BriefEditorRequest } from "../hub/hub-context";
import { useThreadStream } from "../thread/use-thread-stream";
import { useThreadViewer } from "../thread/use-thread-viewer";
import {
  type BriefForm,
  briefFromForm,
  type ClaimDraft,
  formFromBrief,
  formProblem,
  newClaim,
  newTable,
} from "./brief-form";

const PROFILES: { value: ExecutionProfile; label: string }[] = [
  { value: "safe", label: "Safe: fewer, cheaper queries" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep: more hypotheses and queries" },
];

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function FieldLabel({
  htmlFor,
  children,
}: {
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1 mt-3 block text-xs font-semibold text-muted-foreground"
    >
      {children}
    </label>
  );
}

// ----------------------------------------------------------------------------
// Source messages
// ----------------------------------------------------------------------------

export type SourceLookup = (messageId: string) => ThreadMessage | undefined;

function useSourceLookup(
  issueId: string,
  threadIds: (string | null)[],
): SourceLookup {
  const queryClient = useQueryClient();
  return (messageId) => {
    for (const threadId of threadIds) {
      if (!threadId) continue;
      const messages = queryClient.getQueryData<ThreadMessage[]>(
        queryKeys.issueThreads.messages(issueId, threadId),
      );
      const found = messages?.find((m) => m.id === messageId);
      if (found) return found;
    }
    return undefined;
  };
}

function SourceLink({
  messageId,
  lookup,
  scratchThreadId,
}: {
  messageId: string;
  lookup: SourceLookup;
  scratchThreadId: string | null;
}) {
  const [open, setOpen] = useState(false);
  const { nameOf } = useThreadViewer();
  const source = lookup(messageId);
  const who = !source
    ? "a thread message"
    : source.author_kind === "agent"
      ? source.requested_by_user_id
        ? `the agent's answer to ${nameOf(source.requested_by_user_id)}`
        : "the agent's answer"
      : `${nameOf(source.author_user_id)}'s message`;
  const where =
    source && scratchThreadId && source.thread_id === scratchThreadId
      ? " in your scratch chat"
      : "";

  return (
    <div className="text-xs">
      <button
        type="button"
        className="whitespace-nowrap text-primary hover:underline"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        from {who}
        {where} {open ? "▴" : "↗"}
      </button>
      {open && (
        <blockquote className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap border-l-2 border-border pl-2 text-muted-foreground">
          {source
            ? source.body_md || "(no text)"
            : "This message isn't loaded here. It is in the issue's thread."}
        </blockquote>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Claim lists
// ----------------------------------------------------------------------------

function ClaimList({
  label,
  noun,
  claims,
  onChange,
  lookup,
  scratchThreadId,
}: {
  label: string;
  noun: string;
  claims: ClaimDraft[];
  onChange: (claims: ClaimDraft[]) => void;
  lookup: SourceLookup;
  scratchThreadId: string | null;
}) {
  const update = (key: string, patch: Partial<ClaimDraft>) =>
    onChange(claims.map((c) => (c.key === key ? { ...c, ...patch } : c)));

  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      {claims.length === 0 && (
        <p className="text-xs text-muted-foreground">None yet.</p>
      )}
      <ul className="space-y-1.5">
        {claims.map((claim, i) => (
          <li key={claim.key} className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-3 h-4 w-4 flex-none accent-primary"
              checked={claim.include}
              aria-label={`Include ${noun} ${i + 1}`}
              onChange={(e) => update(claim.key, { include: e.target.checked })}
            />
            <div className="min-w-0 flex-1">
              <Input
                aria-label={`${noun} ${i + 1}`}
                value={claim.statement}
                maxLength={500}
                className={cn(!claim.include && "opacity-50 line-through")}
                onChange={(e) =>
                  update(claim.key, { statement: e.target.value })
                }
              />
              {claim.message_id && (
                <SourceLink
                  messageId={claim.message_id}
                  lookup={lookup}
                  scratchThreadId={scratchThreadId}
                />
              )}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="mt-0.5 h-9 w-9 flex-none"
              aria-label={`Remove ${noun} ${i + 1}`}
              onClick={() =>
                onChange(claims.filter((c) => c.key !== claim.key))
              }
            >
              <X className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="mt-1 h-7 gap-1 px-2 text-xs"
        onClick={() => onChange([...claims, newClaim()])}
      >
        <Plus className="h-3 w-3" />
        Add {noun}
      </Button>
    </div>
  );
}

// ----------------------------------------------------------------------------
// The form
// ----------------------------------------------------------------------------

/**
 * "handoff" edits a brief drafted from an issue's thread; "new" starts a run
 * from any page, with nothing to draft from (spec 0001 §8.2).
 */
export type BriefMode = "handoff" | "new";

export interface BriefFormViewProps {
  mode: BriefMode;
  initial: BriefForm;
  /** Finds the thread message a finding came from (hand-off only). */
  lookup?: SourceLookup;
  scratchThreadId?: string | null;
  /** Focus the empty lead a follow-up run adds. */
  focusNewLead?: boolean;
  pending: boolean;
  /** Set when the server couldn't tell which datasource to use. */
  datasourcePrompt?: string | null;
  onSubmit: (form: BriefForm) => void;
  onCancel: () => void;
}

const NO_SOURCE: SourceLookup = () => undefined;

export function BriefFormView({
  mode,
  initial,
  lookup = NO_SOURCE,
  scratchThreadId = null,
  focusNewLead = false,
  pending,
  datasourcePrompt = null,
  onSubmit,
  onCancel,
}: BriefFormViewProps) {
  const [form, setForm] = useState<BriefForm>(initial);
  const [touched, setTouched] = useState(false);
  const datasources = useDataSources();
  const datasourceList = datasources.data ?? [];
  const isNew = mode === "new";
  const problem = formProblem(form, {
    requireTables: isNew,
    requireDatasource: isNew && datasourceList.length > 1,
  });
  const set = (patch: Partial<BriefForm>) =>
    setForm((f) => ({ ...f, ...patch }));

  // Start on the default datasource (or the only one); the table rows change it
  const fallbackDatasource =
    datasourceList.find((d) => d.is_default)?.id ?? datasourceList[0]?.id;
  const datasourceIds = datasourceList.map((d) => d.id).join(",");
  useEffect(() => {
    if (!fallbackDatasource) return;
    setForm((f) =>
      f.datasourceId && datasourceIds.split(",").includes(f.datasourceId)
        ? f
        : { ...f, datasourceId: fallbackDatasource },
    );
  }, [fallbackDatasource, datasourceIds]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (problem) return;
    onSubmit(form);
  };

  const datasourceType =
    datasourceList.find((d) => d.id === form.datasourceId)?.type ??
    "postgresql";

  return (
    <form onSubmit={submit} aria-label="Investigation brief">
      <FieldLabel htmlFor="brief-symptom">Symptom</FieldLabel>
      <Input
        id="brief-symptom"
        value={form.symptom}
        maxLength={1000}
        onChange={(e) => set({ symptom: e.target.value })}
        placeholder="What is wrong, in one or two sentences"
      />

      <ClaimList
        label="Findings (treated as facts)"
        noun="finding"
        claims={form.findings}
        onChange={(findings) => set({ findings })}
        lookup={lookup}
        scratchThreadId={scratchThreadId}
      />
      <ClaimList
        label="Ruled out (not proposed again)"
        noun="exclusion"
        claims={form.ruledOut}
        onChange={(ruledOut) => set({ ruledOut })}
        lookup={lookup}
        scratchThreadId={scratchThreadId}
      />

      {/* A new run has no thread to draft leads from */}
      {!isNew && (
        <>
          <FieldLabel>Leads (tested first)</FieldLabel>
          <ul className="space-y-1.5">
            {form.leads.map((lead, i) => (
              <li key={i} className="flex items-center gap-2">
                <Input
                  aria-label={`Lead ${i + 1}`}
                  value={lead}
                  maxLength={300}
                  autoFocus={
                    i === form.leads.length - 1 && !lead && focusNewLead
                  }
                  placeholder="A suspected cause, or what to look at next"
                  onChange={(e) =>
                    set({
                      leads: form.leads.map((l, j) =>
                        j === i ? e.target.value : l,
                      ),
                    })
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 flex-none"
                  aria-label={`Remove lead ${i + 1}`}
                  onClick={() =>
                    set({ leads: form.leads.filter((_, j) => j !== i) })
                  }
                >
                  <X className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-1 h-7 gap-1 px-2 text-xs"
            onClick={() => set({ leads: [...form.leads, ""] })}
          >
            <Plus className="h-3 w-3" />
            Add lead
          </Button>
        </>
      )}

      <FieldLabel>Table(s)</FieldLabel>
      <div className="space-y-2">
        {form.tables.map((table) => (
          <DatasetEntry
            key={table.key}
            datasourceId={form.datasourceId}
            datasourceType={datasourceType}
            identifier={table.identifier}
            onDatasourceChange={(datasourceId) => set({ datasourceId })}
            onIdentifierChange={(identifier) =>
              set({
                tables: form.tables.map((t) =>
                  t.key === table.key ? { ...t, identifier } : t,
                ),
              })
            }
            onRemove={() =>
              set({ tables: form.tables.filter((t) => t.key !== table.key) })
            }
            canRemove={form.tables.length > 1}
            disabled={pending}
            dataSources={datasourceList}
            onTableSelect={() => undefined}
          />
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-2 w-full border-dashed"
        disabled={pending || datasourceList.length === 0}
        onClick={() => set({ tables: [...form.tables, newTable()] })}
      >
        <Plus className="mr-2 h-4 w-4" />
        Add another table
      </Button>
      {datasourcePrompt && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {datasourcePrompt}
        </p>
      )}
      {datasources.isSuccess && datasourceList.length === 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          No datasources yet.{" "}
          <Link to="/datasources" className="text-primary underline">
            Connect one
          </Link>{" "}
          to investigate its tables.
        </p>
      )}

      <DatePicker
        className="mt-4"
        label="Time window (optional)"
        value={form.window}
        onChange={(window) => set({ window })}
        placeholder="Any time"
        hint="The days the investigation should look at"
      />

      <FieldLabel htmlFor="brief-notes">Notes</FieldLabel>
      <Textarea
        id="brief-notes"
        value={form.notes}
        maxLength={2000}
        rows={3}
        onChange={(e) => set({ notes: e.target.value })}
        placeholder="Anything else the investigation should know"
      />

      <FieldLabel htmlFor="brief-profile">Depth</FieldLabel>
      <select
        id="brief-profile"
        className={selectClass}
        value={form.profile}
        onChange={(e) => set({ profile: e.target.value as ExecutionProfile })}
      >
        {PROFILES.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>

      {touched && problem && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {problem}
        </p>
      )}

      <DialogFooter className="mt-4 gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={pending} className="gap-1.5">
          {pending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Start investigation
        </Button>
      </DialogFooter>
    </form>
  );
}

// ----------------------------------------------------------------------------
// Hand-off: start a run on the issue from its thread's brief
// ----------------------------------------------------------------------------

interface HandoffFormProps {
  issueId: string;
  datasetId: string | null;
  initial: BriefForm;
  sourceThreadId: string | null;
  sharedThreadId: string | null;
  parentRunId: string | null;
  onDone: () => void;
}

function HandoffForm({
  issueId,
  datasetId,
  initial,
  sourceThreadId,
  sharedThreadId,
  parentRunId,
  onDone,
}: HandoffFormProps) {
  const start = useStartRun(issueId);
  const scratchThreadId =
    sourceThreadId && sourceThreadId !== sharedThreadId ? sourceThreadId : null;
  const lookup = useSourceLookup(issueId, [sharedThreadId, scratchThreadId]);

  const submit = async (form: BriefForm) => {
    try {
      await start.mutateAsync({
        brief: briefFromForm(form),
        execution_profile: form.profile,
        dataset_id: datasetId ?? undefined,
        datasource_id: form.datasourceId || undefined,
        source_thread_id: sourceThreadId ?? undefined,
        parent_run_id: parentRunId ?? undefined,
      });
      toast.success("Investigation started", {
        description: "Its card in the thread shows progress and steering.",
      });
      onDone();
    } catch (error) {
      toast.error("Couldn't start the investigation", {
        description: errorText(error),
      });
    }
  };

  return (
    <BriefFormView
      mode="handoff"
      initial={initial}
      lookup={lookup}
      scratchThreadId={scratchThreadId}
      focusNewLead={!!parentRunId}
      pending={start.isPending}
      onSubmit={(form) => void submit(form)}
      onCancel={onDone}
    />
  );
}

// ----------------------------------------------------------------------------
// Waiting for the agent's draft
// ----------------------------------------------------------------------------

function useDraftMessage(
  issueId: string,
  threadId: string | null,
  messageId: string | null,
): ThreadMessage | undefined {
  const messages = useThreadMessages(issueId, threadId);
  const message = messages.data?.find((m) => m.id === messageId);
  const waiting =
    !!messageId &&
    (!message || message.status === "queued" || message.status === "streaming");
  useThreadStream(issueId, threadId, {
    enabled: waiting && messages.isSuccess,
  });
  return message;
}

// ----------------------------------------------------------------------------
// The dialog
// ----------------------------------------------------------------------------

export interface BriefEditorDialogProps {
  issueId: string;
  issueTitle: string;
  datasetId: string | null;
  sharedThreadId: string | null;
  request: BriefEditorRequest | null;
  onClose: () => void;
}

export function BriefEditorDialog({
  issueId,
  issueTitle,
  datasetId,
  sharedThreadId,
  request,
  onClose,
}: BriefEditorDialogProps) {
  const draftThreadId = request?.kind === "draft" ? request.threadId : null;
  const draftMessageId = request?.kind === "draft" ? request.messageId : null;
  const draft = useDraftMessage(issueId, draftThreadId, draftMessageId);
  const [skipDraft, setSkipDraft] = useState(false);

  useEffect(() => setSkipDraft(false), [request]);

  const drafted = draft ? asBrief(draft.payload.brief) : null;
  const draftFailed =
    !!draft && (draft.status === "error" || draft.status === "cancelled");
  const draftError =
    draft && typeof draft.payload.error === "string"
      ? draft.payload.error
      : "The agent couldn't draft a brief.";
  const waiting =
    request?.kind === "draft" && !drafted && !draftFailed && !skipDraft;

  const initialBrief: InvestigationBrief | null = useMemo(() => {
    if (!request) return null;
    if (request.kind === "brief") return request.brief;
    if (drafted) return drafted;
    if (draftFailed || skipDraft) return { symptom: issueTitle };
    return null;
  }, [request, drafted, draftFailed, skipDraft, issueTitle]);

  const sourceThreadId =
    request?.kind === "brief" ? request.sourceThreadId : draftThreadId;
  const parentRunId =
    request?.kind === "brief" ? (request.parentRunId ?? null) : null;
  const formKey =
    request?.kind === "draft"
      ? `${request.messageId}-${drafted ? "draft" : "blank"}`
      : "brief";

  return (
    <Dialog open={!!request} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {parentRunId
              ? "Continue investigating"
              : "Hand off to an investigation"}
          </DialogTitle>
          <DialogDescription>
            {parentRunId
              ? "A follow-up run starts from the previous run's brief and what it concluded. Add what to look at next."
              : "The agent drafts this brief from the thread. Edit anything: only this brief is sent to the manager and its subagents."}
          </DialogDescription>
        </DialogHeader>

        {waiting ? (
          <div className="flex flex-col items-center gap-3 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <p>The agent is drafting a brief from the thread…</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setSkipDraft(true)}
            >
              Write it myself
            </Button>
          </div>
        ) : (
          <>
            {draftFailed && !drafted && (
              <p
                role="alert"
                className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
              >
                {draftError} You can write the brief yourself.
              </p>
            )}
            {initialBrief && (
              <HandoffForm
                key={formKey}
                issueId={issueId}
                datasetId={datasetId}
                initial={formFromBrief(initialBrief)}
                sourceThreadId={sourceThreadId}
                sharedThreadId={sharedThreadId}
                parentRunId={parentRunId}
                onDone={onClose}
              />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
