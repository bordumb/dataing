/**
 * The thread's first entry: who opened the issue, with its description as
 * the body (spec 0001 §8.1). There is no separate description card. An issue
 * a person opened reads "Maya opened the issue" and its author can edit the
 * description here; one dataing opened (a check, an alert, the API) starts
 * with an event line instead.
 */

import { useState } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/error-message";
import type { ThreadMessage } from "@/lib/api/issue-threads";
import { useIssue, useUpdateIssue } from "@/lib/api/issues";

import { Avatar, Meta, colorFor, formatTime } from "./message-parts";
import type { ThreadViewer } from "./ThreadMessageItem";

/** The `created` event the server appends when it opens an issue. */
export function isIssueOpenedEvent(message: ThreadMessage): boolean {
  return message.kind === "event" && message.payload.event_type === "created";
}

export interface IssueOpenedEntryProps {
  issueId: string;
  /** Who opened it; null when dataing did. */
  openerId: string | null;
  /** Where a dataing-opened issue came from, e.g. an alerting tool. */
  sourceProvider: string | null;
  openedAt: string;
  viewer: ThreadViewer;
}

function DescriptionEditor({
  issueId,
  description,
  onDone,
}: {
  issueId: string;
  description: string;
  onDone: () => void;
}) {
  const [draft, setDraft] = useState(description);
  const update = useUpdateIssue();

  const save = async () => {
    try {
      await update.mutateAsync({
        issueId,
        data: { description: draft.trim() || null },
      });
      onDone();
    } catch (error) {
      toast.error("Couldn't save the description", {
        description: errorText(error),
      });
    }
  };

  return (
    <div className="space-y-2">
      <Textarea
        aria-label="Edit description"
        value={draft}
        rows={4}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void save();
          }
          if (e.key === "Escape") onDone();
        }}
        placeholder="What's wrong, where it shows and since when (Markdown)"
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => void save()}
          disabled={update.isPending}
        >
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function IssueOpenedEntry({
  issueId,
  openerId,
  sourceProvider,
  openedAt,
  viewer,
}: IssueOpenedEntryProps) {
  const issue = useIssue(issueId);
  const [editing, setEditing] = useState(false);
  const description = issue.data?.description ?? null;

  if (!openerId) {
    return (
      <div className="py-1.5">
        <p className="py-1 pl-9 text-[12.5px] text-muted-foreground">
          <span aria-hidden>⚑ </span>Issue opened by dataing
          {sourceProvider ? ` from ${sourceProvider}` : ""} ·{" "}
          {formatTime(openedAt)}
        </p>
        {description && (
          <div className="pb-1 pl-9 text-sm">
            <Markdown>{description}</Markdown>
          </div>
        )}
      </div>
    );
  }

  const name = viewer.nameOf(openerId);
  const isAuthor = !!viewer.userId && viewer.userId === openerId;
  return (
    <div className="flex gap-2.5 py-2.5">
      <Avatar
        label={name.charAt(0).toUpperCase()}
        className={colorFor(openerId)}
      />
      <div className="min-w-0 flex-1">
        <Meta>
          <span className="font-semibold text-foreground">{name}</span> · opened
          the issue · {formatTime(openedAt)}
        </Meta>
        {editing ? (
          <DescriptionEditor
            issueId={issueId}
            description={description ?? ""}
            onDone={() => setEditing(false)}
          />
        ) : description ? (
          <Markdown>{description}</Markdown>
        ) : issue.isSuccess ? (
          <p className="text-sm text-muted-foreground">No description.</p>
        ) : null}
        {isAuthor && !editing && issue.isSuccess && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 h-6 px-2 text-xs text-muted-foreground"
            onClick={() => setEditing(true)}
          >
            Edit
          </Button>
        )}
      </div>
    </div>
  );
}

/** The `created` event, rendered as the issue's opening entry. */
export function IssueOpenedMessage({
  message,
  issueId,
  viewer,
}: {
  message: ThreadMessage;
  issueId: string;
  viewer: ThreadViewer;
}) {
  const source = message.payload.source_provider;
  return (
    <IssueOpenedEntry
      issueId={issueId}
      openerId={message.author_user_id}
      sourceProvider={typeof source === "string" && source ? source : null}
      openedAt={message.created_at}
      viewer={viewer}
    />
  );
}
