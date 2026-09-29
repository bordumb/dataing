/**
 * One entry in an issue thread, rendered by kind.
 */

import { useState } from "react";
import { AlertCircle, FileText, Loader2, Square } from "lucide-react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import {
  useCancelAnswer,
  useDeleteMessage,
  useEditMessage,
  type AgentReplyPayload,
  type SteerProposal,
  type ThreadMessage,
} from "@/lib/api/issue-threads";
import { errorText } from "@/lib/api/error-message";
import {
  asBrief,
  isFailedOutcome,
  type InvestigationBrief,
  type InvestigationOutcome,
} from "@/lib/api/investigation-runs";
import {
  findRun,
  runNumbers,
  useIssueInvestigationRuns,
} from "@/lib/api/issues";

import { useIssueHub } from "../hub/hub-context";
import {
  InvestigationCard,
  type InvestigationPayload,
} from "./InvestigationCard";
import { IssueOpenedMessage, isIssueOpenedEvent } from "./IssueOpened";
import {
  Avatar,
  Meta,
  SYSTEM_AVATAR,
  colorFor,
  formatTime,
} from "./message-parts";
import { OutcomeCard } from "./OutcomeCard";
import { Pill } from "./Pill";
import { ProposalCard, type SentProposal } from "./ProposalCard";
import { ToolCalls } from "./ToolCalls";

export interface ThreadViewer {
  userId: string | null;
  isAdmin: boolean;
  /** Members hand off, steer and review; viewers read and comment. */
  canWrite: boolean;
  nameOf: (userId: string | null | undefined) => string;
}

/** Facts about the whole thread that single messages need. */
export interface ThreadFacts {
  /** Each finished run's outcome, by investigation id. */
  outcomes: Map<string, InvestigationOutcome>;
  /** The brief each run started with, by investigation id. */
  briefs: Map<string, InvestigationBrief>;
  /** Steers people sent from agent proposals, by the proposing reply's id. */
  sentProposals: Map<string, SentProposal[]>;
}

export const EMPTY_FACTS: ThreadFacts = {
  outcomes: new Map(),
  briefs: new Map(),
  sentProposals: new Map(),
};

/** Collect the facts messages need from the thread's messages. */
export function threadFacts(messages: ThreadMessage[]): ThreadFacts {
  const outcomes = new Map<string, InvestigationOutcome>();
  const briefs = new Map<string, InvestigationBrief>();
  const sentProposals = new Map<string, SentProposal[]>();
  for (const m of messages) {
    const id = m.payload.investigation_id;
    if (m.kind === "investigation" && typeof id === "string") {
      if (m.payload.phase === "outcome") {
        if (m.payload.outcome) {
          outcomes.set(id, m.payload.outcome as InvestigationOutcome);
        }
      } else {
        const brief = asBrief(m.payload.brief);
        if (brief) briefs.set(id, brief);
      }
    }
    const replyId = m.payload.proposal_message_id;
    if (m.kind === "steer" && m.author_kind === "user" && replyId) {
      const sent = sentProposals.get(String(replyId)) ?? [];
      sent.push({
        kind: String(m.payload.kind ?? ""),
        hypothesis_id: (m.payload.hypothesis_id as string | null) ?? null,
        author_user_id: m.author_user_id,
      });
      sentProposals.set(String(replyId), sent);
    }
  }
  return { outcomes, briefs, sentProposals };
}

/** The steer already sent for a proposal, matched by kind and hypothesis. */
function sentFor(
  sent: SentProposal[] | undefined,
  proposal: SteerProposal,
): SentProposal | null {
  return (
    sent?.find(
      (s) =>
        s.kind === proposal.kind &&
        (s.hypothesis_id ?? null) === (proposal.hypothesis_id ?? null),
    ) ?? null
  );
}

interface MessageProps {
  message: ThreadMessage;
  issueId: string;
  threadId: string;
  viewer: ThreadViewer;
  facts?: ThreadFacts;
}

// ----------------------------------------------------------------------------
// Comments
// ----------------------------------------------------------------------------

function CommentMessage({ message, issueId, threadId, viewer }: MessageProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.body_md);
  const edit = useEditMessage(issueId, threadId);
  const remove = useDeleteMessage(issueId, threadId);
  const name = viewer.nameOf(message.author_user_id);
  const isAuthor = !!viewer.userId && message.author_user_id === viewer.userId;
  const deleted = message.deleted_at !== null;

  const save = async () => {
    const body = draft.trim();
    if (!body) return;
    try {
      await edit.mutateAsync({ messageId: message.id, bodyMd: body });
      setEditing(false);
    } catch (error) {
      toast.error("Couldn't save the comment", {
        description: errorText(error),
      });
    }
  };

  const onDelete = async () => {
    if (!window.confirm("Delete this comment?")) return;
    try {
      await remove.mutateAsync(message.id);
    } catch (error) {
      toast.error("Couldn't delete the comment", {
        description: errorText(error),
      });
    }
  };

  return (
    <div className="flex gap-2.5 py-2.5">
      <Avatar
        label={name.charAt(0).toUpperCase()}
        className={colorFor(message.author_user_id ?? name)}
      />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">{name}</span>
          {message.asks_agent ? " · asked the agent" : ""} ·{" "}
          {formatTime(message.created_at)}
          {message.edited_at && !deleted ? " · edited" : ""}
        </Meta>
        {deleted ? (
          <p className="text-sm italic text-muted-foreground">
            This comment was deleted.
          </p>
        ) : editing ? (
          <div className="space-y-2">
            <Textarea
              aria-label="Edit comment"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void save();
                }
                if (e.key === "Escape") setEditing(false);
              }}
              rows={3}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={save}
                disabled={edit.isPending || !draft.trim()}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(message.body_md);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : message.asks_agent ? (
          // "@agent is it every region?", with the pill inline as in the mockup.
          <div className="flex items-start gap-1.5">
            <Pill tone="agent" className="mt-0.5 flex-none">
              @agent
            </Pill>
            <div className="min-w-0 flex-1">
              <Markdown>{message.body_md}</Markdown>
            </div>
          </div>
        ) : (
          <Markdown>{message.body_md}</Markdown>
        )}
        {!deleted && !editing && (isAuthor || viewer.isAdmin) && (
          <div className="mt-1 flex gap-1">
            {isAuthor && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs text-muted-foreground"
                onClick={() => {
                  setDraft(message.body_md);
                  setEditing(true);
                }}
              >
                Edit
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground"
              onClick={onDelete}
              disabled={remove.isPending}
            >
              Delete
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Agent replies
// ----------------------------------------------------------------------------

/** The steers a reply proposes, naming each run by its number ("#7"). */
function Proposals({
  proposals,
  message,
  issueId,
  viewer,
  facts,
}: {
  proposals: SteerProposal[];
  message: ThreadMessage;
  issueId: string;
  viewer: ThreadViewer;
  facts: ThreadFacts;
}) {
  const runs = useIssueInvestigationRuns(issueId);
  const allRuns = runs.data?.items ?? [];
  const numbers = runNumbers(allRuns);
  return (
    <>
      {proposals.map((proposal, i) => {
        const run = findRun(allRuns, { investigationId: proposal.run_id });
        return (
          <ProposalCard
            key={i}
            proposal={proposal}
            runNumber={run ? numbers.get(run.id) : undefined}
            replyId={message.id}
            canWrite={viewer.canWrite}
            sent={sentFor(facts.sentProposals.get(message.id), proposal)}
            nameOf={viewer.nameOf}
          />
        );
      })}
    </>
  );
}

function AgentReplyMessage({
  message,
  issueId,
  threadId,
  viewer,
  facts = EMPTY_FACTS,
}: MessageProps) {
  const cancel = useCancelAnswer(issueId, threadId);
  const payload = message.payload as AgentReplyPayload;
  const toolCalls = payload.tool_calls ?? [];
  const proposals = payload.proposals ?? [];
  const running = message.status === "queued" || message.status === "streaming";
  const asker = message.requested_by_user_id;
  const canCancel =
    running && ((!!viewer.userId && asker === viewer.userId) || viewer.isAdmin);

  const onCancel = async () => {
    try {
      await cancel.mutateAsync(message.id);
    } catch (error) {
      toast.error("Couldn't cancel the answer", {
        description: errorText(error),
      });
    }
  };

  return (
    <div className="flex gap-2.5 py-2.5" aria-busy={running}>
      <Avatar label="AI" className="bg-violet-600" />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">Agent</span>
          {asker ? ` · replying to ${viewer.nameOf(asker)}` : ""}
          {asker ? ` · ran as ${viewer.nameOf(asker)}` : ""} ·{" "}
          {formatTime(message.created_at)}
        </Meta>

        {message.body_md && <Markdown>{message.body_md}</Markdown>}

        {message.status === "queued" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Waiting for the agent…
          </p>
        )}
        {message.status === "streaming" && (
          <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Answering…
          </p>
        )}
        {message.status === "error" && (
          <p className="mt-1 flex items-start gap-1.5 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-none" />
            {payload.error || "The agent couldn't answer."}
          </p>
        )}
        {message.status === "cancelled" && (
          <p className="mt-1 text-xs italic text-muted-foreground">
            Cancelled.
          </p>
        )}

        <ToolCalls calls={toolCalls} issueId={issueId} threadId={threadId} />

        {message.status === "complete" && proposals.length > 0 && (
          <Proposals
            proposals={proposals}
            message={message}
            issueId={issueId}
            viewer={viewer}
            facts={facts}
          />
        )}

        {canCancel && (
          <Button
            variant="outline"
            size="sm"
            className="mt-2 h-7 gap-1 text-xs"
            onClick={onCancel}
            disabled={cancel.isPending}
          >
            <Square className="h-3 w-3" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Everything else
// ----------------------------------------------------------------------------

function EventMessage({ message }: { message: ThreadMessage }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-1 py-1.5 pl-9 text-xs text-muted-foreground">
      <Markdown className="text-xs [&_p]:my-0">{message.body_md}</Markdown>
      <span>· {formatTime(message.created_at)}</span>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  published: "shared from a scratch chat",
};

function CardMessage({ message, viewer }: MessageProps) {
  const author = authorName(message, viewer);
  return (
    <div className="flex gap-2.5 py-2.5">
      <AuthorAvatar message={message} author={author} />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">{author}</span> ·{" "}
          {KIND_LABEL[message.kind] ?? message.kind} ·{" "}
          {formatTime(message.created_at)}
        </Meta>
        <div className="rounded-lg border border-border px-3 py-2">
          {message.body_md ? (
            <Markdown>{message.body_md}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground">No details.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Investigations and briefs
// ----------------------------------------------------------------------------

function AuthorAvatar({
  message,
  author,
  system = false,
}: {
  message: ThreadMessage;
  author: string;
  /** Attributed to dataing itself, whatever the author kind. */
  system?: boolean;
}) {
  if (message.author_kind === "agent" && !system) {
    return <Avatar label="AI" className="bg-violet-600" />;
  }
  return (
    <Avatar
      label={author.charAt(0).toUpperCase()}
      className={
        system || message.author_kind === "system"
          ? SYSTEM_AVATAR
          : colorFor(message.author_user_id ?? author)
      }
    />
  );
}

function authorName(message: ThreadMessage, viewer: ThreadViewer): string {
  if (message.author_kind === "agent") return "Agent";
  if (message.author_kind === "system") return "dataing";
  return viewer.nameOf(message.author_user_id);
}

function InvestigationMessage({
  message,
  issueId,
  viewer,
  facts = EMPTY_FACTS,
}: MessageProps) {
  const isOutcome = message.payload.phase === "outcome";
  const payload = message.payload as InvestigationPayload & {
    outcome?: InvestigationOutcome;
  };
  const investigationId = payload.investigation_id ?? null;
  const runs = useIssueInvestigationRuns(issueId);
  const allRuns = runs.data?.items ?? [];
  const run = findRun(allRuns, { runId: payload.run_id, investigationId });
  const number = run ? runNumbers(allRuns).get(run.id) : undefined;
  // A run nobody started by hand (the API, a webhook, a check) is dataing's.
  const headless = !isOutcome && message.author_user_id == null;
  const author = headless ? "dataing" : authorName(message, viewer);
  const fromScratch =
    !!payload.source_thread_id &&
    payload.source_thread_id !== message.thread_id;
  const which = number ? `investigation #${number}` : "investigation";
  return (
    <div className="flex gap-2.5 py-2.5">
      <AuthorAvatar message={message} author={author} system={headless} />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">{author}</span> ·{" "}
          {isOutcome
            ? `${which} ${isFailedOutcome(payload.outcome) ? "failed" : "finished"}`
            : payload.parent_run_id
              ? "continued investigating"
              : fromScratch
                ? "started an investigation from a scratch chat"
                : "started an investigation"}{" "}
          · {formatTime(message.created_at)}
        </Meta>
        {isOutcome ? (
          <OutcomeCard
            message={message}
            issueId={issueId}
            run={run}
            number={number}
            brief={
              (investigationId ? facts.briefs.get(investigationId) : null) ??
              asBrief(run?.brief)
            }
            canWrite={viewer.canWrite}
            nameOf={viewer.nameOf}
          />
        ) : (
          <InvestigationCard
            message={message}
            run={run}
            number={number}
            canWrite={viewer.canWrite}
            nameOf={viewer.nameOf}
            outcome={
              investigationId ? facts.outcomes.get(investigationId) : null
            }
          />
        )}
      </div>
    </div>
  );
}

function BriefMessage({ message, threadId, viewer }: MessageProps) {
  const hub = useIssueHub();
  const brief = asBrief(message.payload.brief);
  const asker = message.requested_by_user_id;
  const drafting =
    message.status === "queued" || message.status === "streaming";
  const error =
    typeof message.payload.error === "string" ? message.payload.error : null;

  return (
    <div className="flex gap-2.5 py-2.5" aria-busy={drafting}>
      <Avatar label="AI" className="bg-violet-600" />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">Agent</span> ·
          investigation brief
          {asker ? ` for ${viewer.nameOf(asker)}` : ""} ·{" "}
          {formatTime(message.created_at)}
        </Meta>
        <div className="rounded-lg border border-border px-3 py-2">
          {drafting ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Drafting a brief from the thread…
            </p>
          ) : message.status === "error" ? (
            <p className="flex items-start gap-1.5 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-none" />
              {error || "The agent couldn't draft a brief."}
            </p>
          ) : message.status === "cancelled" ? (
            <p className="text-xs italic text-muted-foreground">Cancelled.</p>
          ) : (
            <Markdown>{message.body_md}</Markdown>
          )}
          {brief && hub?.canWrite && (
            <Button
              variant="outline"
              size="sm"
              className="mt-2 h-7 gap-1 text-xs"
              onClick={() =>
                hub.openBriefEditor({
                  kind: "brief",
                  brief,
                  sourceThreadId: threadId,
                })
              }
            >
              <FileText className="h-3 w-3" />
              Edit and start
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

const STEER_OUTCOME_TONE: Record<string, "ok" | "bad" | "warn"> = {
  applied: "ok",
  rejected: "bad",
  pending: "warn",
};

/** A person's steer, or the run's note on how a steer ended. */
function SteerMessage({ message, viewer }: MessageProps) {
  const author = authorName(message, viewer);
  const status =
    typeof message.payload.status === "string" ? message.payload.status : null;
  return (
    <div className="flex gap-2.5 py-2.5">
      <AuthorAvatar message={message} author={author} />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">{author}</span> ·{" "}
          {message.author_kind === "user"
            ? "steered the investigation"
            : "steer outcome"}{" "}
          · {formatTime(message.created_at)}
        </Meta>
        <div className="flex flex-wrap items-baseline gap-1.5 rounded border-l-[3px] border-violet-500 bg-violet-50 px-2 py-1 text-sm dark:bg-violet-950/40">
          {status && (
            <Pill tone={STEER_OUTCOME_TONE[status] ?? "warn"}>
              {status === "rejected" ? "not applied" : status}
            </Pill>
          )}
          <Markdown className="[&_p]:my-0">{message.body_md}</Markdown>
        </div>
      </div>
    </div>
  );
}

function renderMessage(props: MessageProps) {
  switch (props.message.kind) {
    case "comment":
      return <CommentMessage {...props} />;
    case "agent_reply":
      return <AgentReplyMessage {...props} />;
    case "event":
      return isIssueOpenedEvent(props.message) ? (
        <IssueOpenedMessage {...props} />
      ) : (
        <EventMessage message={props.message} />
      );
    case "investigation":
      return <InvestigationMessage {...props} />;
    case "brief":
      return <BriefMessage {...props} />;
    case "steer":
      return <SteerMessage {...props} />;
    default:
      return <CardMessage {...props} />;
  }
}

export function ThreadMessageItem(props: MessageProps) {
  return (
    <div id={`message-${props.message.id}`} className="scroll-mt-20">
      {renderMessage(props)}
    </div>
  );
}
