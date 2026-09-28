/**
 * One entry in an issue thread, rendered by kind.
 */

import { useState } from "react";
import { format, isToday } from "date-fns";
import { AlertCircle, Loader2, Square } from "lucide-react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import {
  useCancelAnswer,
  useDeleteMessage,
  useEditMessage,
  type AgentReplyPayload,
  type ThreadMessage,
} from "@/lib/api/issue-threads";
import { errorText } from "@/lib/api/error-message";
import { cn } from "@/lib/utils";

import { ToolCalls } from "./ToolCalls";

export interface ThreadViewer {
  userId: string | null;
  isAdmin: boolean;
  nameOf: (userId: string | null | undefined) => string;
}

interface MessageProps {
  message: ThreadMessage;
  issueId: string;
  threadId: string;
  viewer: ThreadViewer;
}

function formatTime(iso: string): string {
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

function colorFor(key: string): string {
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function Avatar({ label, className }: { label: string; className: string }) {
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

function Meta({ children }: { children: React.ReactNode }) {
  return <div className="mb-0.5 text-xs text-muted-foreground">{children}</div>;
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
        ) : (
          <>
            {message.asks_agent && (
              <Badge
                variant="outline"
                className="mb-1 border-transparent bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300"
              >
                @agent
              </Badge>
            )}
            <Markdown>{message.body_md}</Markdown>
          </>
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

function AgentReplyMessage({
  message,
  issueId,
  threadId,
  viewer,
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

        {proposals.map((proposal, i) => (
          <div
            key={i}
            className="mt-2 rounded-md border border-dashed border-violet-400 px-3 py-2 text-sm"
          >
            <span className="font-semibold">Proposed steer</span> ·{" "}
            {proposal.kind.replace(/_/g, " ")}
            <p className="mt-1">{proposal.text}</p>
          </div>
        ))}

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
  brief: "Investigation brief",
  steer: "Steer",
  investigation: "Investigation",
  published: "Shared from a scratch chat",
};

function CardMessage({ message, viewer }: MessageProps) {
  const author =
    message.author_kind === "agent"
      ? "Agent"
      : message.author_kind === "system"
        ? "dataing"
        : viewer.nameOf(message.author_user_id);
  return (
    <div className="flex gap-2.5 py-2.5">
      {message.author_kind === "agent" ? (
        <Avatar label="AI" className="bg-violet-600" />
      ) : (
        <Avatar
          label={author.charAt(0).toUpperCase()}
          className={
            message.author_kind === "system"
              ? "bg-zinc-500"
              : colorFor(message.author_user_id ?? author)
          }
        />
      )}
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
            <p className="text-sm text-muted-foreground">
              {message.status === "streaming" || message.status === "queued"
                ? "Drafting…"
                : "No details."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function ThreadMessageItem(props: MessageProps) {
  switch (props.message.kind) {
    case "comment":
      return <CommentMessage {...props} />;
    case "agent_reply":
      return <AgentReplyMessage {...props} />;
    case "event":
      return <EventMessage message={props.message} />;
    default:
      return <CardMessage {...props} />;
  }
}
