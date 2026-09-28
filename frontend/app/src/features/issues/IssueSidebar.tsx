/**
 * Issue sidebar: status, assignee, priority, severity, labels and context.
 *
 * The status menu offers only the moves the server says will succeed
 * (allowed_transitions). When a move still needs a field
 * (transition_requirements), the sidebar asks for it inline and sends both in
 * one PATCH. Every failed change shows the server's message in a toast.
 */

import { useState } from "react";
import {
  ChevronDown,
  Clock,
  Eye,
  EyeOff,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/error-message";
import {
  ISSUE_PRIORITIES,
  ISSUE_SEVERITIES,
  getSeverityLabel,
  getStatusLabel,
  getStatusVariant,
  useIssueInvestigationRuns,
  useIssueWatchers,
  useInvalidateIssues,
  useUnwatchIssue,
  useUpdateIssue,
  useWatchIssue,
  type IssueResponse,
  type IssueUpdate,
} from "@/lib/api/issues";
import { useUserDirectory, displayName } from "@/lib/api/users";
import { useJwtAuth } from "@/lib/auth/jwt-context";
import { useRole } from "@/lib/auth/use-role";
import { formatDate } from "@/lib/utils";

const NONE = "__none__";

/** Send a PATCH and toast the server's message on failure. */
function useIssuePatch(issueId: string) {
  const update = useUpdateIssue();
  const patch = async (data: IssueUpdate, failure: string) => {
    try {
      await update.mutateAsync({ issueId, data });
      return true;
    } catch (error) {
      toast.error(failure, { description: errorText(error) });
      return false;
    }
  };
  return { patch, isPending: update.isPending };
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-1.5 mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground first:mt-0">
      {children}
    </h3>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-8 items-center justify-between gap-3 py-0.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex min-w-0 justify-end">{children}</div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Status
// ----------------------------------------------------------------------------

interface StatusSectionProps {
  issue: IssueResponse;
  canEdit: boolean;
}

/** The root cause of the issue's most recently confirmed run, if any. */
function useConfirmedCause(issueId: string): string | null {
  const runs = useIssueInvestigationRuns(issueId);
  const confirmed = (runs.data?.items ?? [])
    .filter((r) => r.outcome_verdict === "confirmed" && r.synthesis_summary)
    .sort((a, b) =>
      String(b.outcome_reviewed_at ?? "").localeCompare(
        String(a.outcome_reviewed_at ?? ""),
      ),
    );
  return confirmed[0]?.synthesis_summary ?? null;
}

function StatusSection({ issue, canEdit }: StatusSectionProps) {
  const { patch, isPending } = useIssuePatch(issue.id);
  const { user } = useJwtAuth();
  const [target, setTarget] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const needs = target ? (issue.transition_requirements[target] ?? []) : [];
  const needsAssignee = needs.includes("assignee_user_id");
  const needsNote = needs.includes("resolution_note");
  const confirmedCause = useConfirmedCause(issue.id);
  // Resolving after a confirmed outcome always asks for the note, pre-filled.
  const asksNote = needsNote || (target === "resolved" && !!confirmedCause);

  const move = async (status: string, extra: IssueUpdate = {}) => {
    const ok = await patch(
      { status, ...extra },
      `Couldn't move the issue to ${getStatusLabel(status)}`,
    );
    if (ok) {
      setTarget(null);
      setNote("");
    }
  };

  const choose = (status: string) => {
    const prefill = status === "resolved" ? confirmedCause : null;
    if ((issue.transition_requirements[status] ?? []).length > 0 || prefill) {
      setTarget(status);
      setNote(prefill ?? "");
      return;
    }
    setTarget(null);
    void move(status);
  };

  const confirm = () => {
    if (!target) return;
    const extra: IssueUpdate = {};
    if (needsAssignee && user) extra.assignee_user_id = user.id;
    if (asksNote && note.trim()) extra.resolution_note = note.trim();
    void move(target, extra);
  };

  return (
    <div>
      <SectionTitle>Status</SectionTitle>
      <div className="flex items-center justify-between gap-2">
        <Badge variant={getStatusVariant(issue.status)}>
          {getStatusLabel(issue.status)}
        </Badge>
        {canEdit && issue.allowed_transitions.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                disabled={isPending}
              >
                {isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : null}
                Change status
                <ChevronDown className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[12rem]">
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                Moves that will succeed
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {issue.allowed_transitions.map((status) => (
                <DropdownMenuItem key={status} onSelect={() => choose(status)}>
                  {getStatusLabel(status)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {target && (
        <div
          role="group"
          aria-label={`Move to ${getStatusLabel(target)}`}
          className="mt-2 space-y-2 rounded-md border border-border bg-muted/40 p-2.5 text-sm"
        >
          {needsAssignee && (
            <p>
              {getStatusLabel(target)} needs an owner. Assign it to yourself?
            </p>
          )}
          {asksNote && (
            <div className="space-y-1">
              <label
                htmlFor="resolution-note"
                className="text-xs font-medium text-muted-foreground"
              >
                Resolution note
              </label>
              <Textarea
                id="resolution-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="What was wrong and how it was fixed"
                rows={3}
              />
            </div>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              className="h-7 text-xs"
              onClick={confirm}
              disabled={isPending || (needsNote && !note.trim())}
            >
              {needsAssignee
                ? `Assign to me and move to ${getStatusLabel(target)}`
                : `Move to ${getStatusLabel(target)}`}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setTarget(null)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Fields
// ----------------------------------------------------------------------------

interface FieldSelectProps {
  label: string;
  value: string | null;
  options: { value: string; label: string }[];
  emptyLabel: string;
  disabled: boolean;
  onChange: (value: string | null) => void;
}

function FieldSelect({
  label,
  value,
  options,
  emptyLabel,
  disabled,
  onChange,
}: FieldSelectProps) {
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
      disabled={disabled}
    >
      <SelectTrigger aria-label={label} className="h-7 w-40 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{emptyLabel}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function LabelsEditor({
  issue,
  canEdit,
}: {
  issue: IssueResponse;
  canEdit: boolean;
}) {
  const { patch, isPending } = useIssuePatch(issue.id);
  const [draft, setDraft] = useState("");

  const setLabels = (labels: string[]) =>
    patch({ labels }, "Couldn't update the labels");

  const add = async () => {
    const label = draft.trim().toLowerCase();
    if (!label) return;
    if (issue.labels.includes(label)) {
      setDraft("");
      return;
    }
    if (await setLabels([...issue.labels, label])) setDraft("");
  };

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1">
        {issue.labels.length === 0 && (
          <span className="text-sm text-muted-foreground">None</span>
        )}
        {issue.labels.map((label) => (
          <Badge key={label} variant="outline" className="gap-1 text-xs">
            {label}
            {canEdit && (
              <button
                type="button"
                aria-label={`Remove label ${label}`}
                className="hover:text-destructive"
                disabled={isPending}
                onClick={() =>
                  void setLabels(issue.labels.filter((l) => l !== label))
                }
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </Badge>
        ))}
      </div>
      {canEdit && (
        <div className="flex gap-1">
          <Input
            aria-label="Add label"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void add();
              }
            }}
            placeholder="Add a label"
            className="h-7 text-xs"
            disabled={isPending}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            aria-label="Add label"
            onClick={() => void add()}
            disabled={isPending || !draft.trim()}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
      )}
    </div>
  );
}

function WatchersSection({ issueId }: { issueId: string }) {
  const watchers = useIssueWatchers(issueId);
  const watch = useWatchIssue();
  const unwatch = useUnwatchIssue();
  const invalidate = useInvalidateIssues();
  const { user } = useJwtAuth();
  const { nameOf } = useUserDirectory();
  const items = watchers.data?.items ?? [];
  const isWatching = !!user && items.some((w) => w.user_id === user.id);
  const isPending = watch.isPending || unwatch.isPending;

  const toggle = async () => {
    try {
      if (isWatching) await unwatch.mutateAsync({ issueId });
      else await watch.mutateAsync({ issueId });
      invalidate.invalidateWatchers(issueId);
    } catch (error) {
      toast.error(
        isWatching ? "Couldn't stop watching" : "Couldn't watch the issue",
        { description: errorText(error) },
      );
    }
  };

  return (
    <div>
      <div className="mb-1.5 mt-4 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Watchers
        </h3>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1 px-2 text-xs"
          onClick={toggle}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : isWatching ? (
            <EyeOff className="h-3 w-3" />
          ) : (
            <Eye className="h-3 w-3" />
          )}
          {isWatching ? "Unwatch" : "Watch"}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        {items.length === 0
          ? "Nobody is watching yet."
          : items.map((w) => nameOf(w.user_id)).join(", ")}
      </p>
    </div>
  );
}

function formatObservedAt(value: string): string {
  // Dates from the create form are plain YYYY-MM-DD; keep them as written.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatDate(value);
}

// ----------------------------------------------------------------------------
// Sidebar
// ----------------------------------------------------------------------------

export function IssueSidebar({ issue }: { issue: IssueResponse }) {
  const { isMember } = useRole();
  const { user } = useJwtAuth();
  const { users, nameOf } = useUserDirectory();
  const { patch, isPending } = useIssuePatch(issue.id);
  const observedAt =
    typeof issue.context?.observed_at === "string"
      ? issue.context.observed_at
      : null;
  const column =
    typeof issue.context?.column === "string" ? issue.context.column : null;

  const assigneeOptions = users
    .filter((u) => u.is_active || u.id === issue.assignee_user_id)
    .map((u) => ({
      value: u.id,
      label: u.id === user?.id ? `${displayName(u)} (you)` : displayName(u),
    }));
  if (
    issue.assignee_user_id &&
    !assigneeOptions.some((o) => o.value === issue.assignee_user_id)
  ) {
    assigneeOptions.push({
      value: issue.assignee_user_id,
      label: nameOf(issue.assignee_user_id),
    });
  }

  return (
    <Card>
      <CardContent className="pt-4">
        <StatusSection issue={issue} canEdit={isMember} />

        <SectionTitle>Details</SectionTitle>
        <Field label="Assignee">
          {isMember ? (
            <FieldSelect
              label="Assignee"
              value={issue.assignee_user_id ?? null}
              options={assigneeOptions}
              emptyLabel="Unassigned"
              disabled={isPending}
              onChange={(v) =>
                void patch(
                  { assignee_user_id: v },
                  "Couldn't change the assignee",
                )
              }
            />
          ) : (
            <span>
              {issue.assignee_user_id
                ? nameOf(issue.assignee_user_id)
                : "Unassigned"}
            </span>
          )}
        </Field>
        <Field label="Priority">
          {isMember ? (
            <FieldSelect
              label="Priority"
              value={issue.priority ?? null}
              options={ISSUE_PRIORITIES.map((p) => ({ value: p, label: p }))}
              emptyLabel="No priority"
              disabled={isPending}
              onChange={(v) =>
                void patch({ priority: v }, "Couldn't change the priority")
              }
            />
          ) : (
            <span>{issue.priority ?? "None"}</span>
          )}
        </Field>
        <Field label="Severity">
          {isMember ? (
            <FieldSelect
              label="Severity"
              value={issue.severity ?? null}
              options={ISSUE_SEVERITIES.map((s) => ({
                value: s,
                label: getSeverityLabel(s),
              }))}
              emptyLabel="No severity"
              disabled={isPending}
              onChange={(v) =>
                void patch({ severity: v }, "Couldn't change the severity")
              }
            />
          ) : (
            <span>
              {issue.severity ? getSeverityLabel(issue.severity) : "None"}
            </span>
          )}
        </Field>
        {observedAt && (
          <Field label="Observed">
            <span>{formatObservedAt(observedAt)}</span>
          </Field>
        )}
        {column && (
          <Field label="Column">
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              {column}
            </code>
          </Field>
        )}
        {issue.due_at && (
          <Field label="Due">
            <span>{formatDate(issue.due_at)}</span>
          </Field>
        )}

        <SectionTitle>Labels</SectionTitle>
        <LabelsEditor issue={issue} canEdit={isMember} />

        {issue.dataset_id && (
          <>
            <SectionTitle>Dataset</SectionTitle>
            <code className="break-all rounded bg-muted px-1.5 py-0.5 text-xs">
              {issue.dataset_id}
            </code>
          </>
        )}

        <WatchersSection issueId={issue.id} />

        <SectionTitle>Timeline</SectionTitle>
        <div className="space-y-0.5 text-xs text-muted-foreground">
          <p className="flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            Created {formatDate(issue.created_at)}
          </p>
          <p className="pl-[18px]">Updated {formatDate(issue.updated_at)}</p>
          {issue.closed_at && (
            <p className="pl-[18px]">Closed {formatDate(issue.closed_at)}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
