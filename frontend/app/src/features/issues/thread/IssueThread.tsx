/**
 * The issue's shared thread: comments, agent answers and events, live.
 *
 * Laid out like the mockup (spec 0001 §8.1): a head with the Shared thread /
 * My scratch chats tabs and "N watching · live", the entries (the first says
 * who opened the issue, with its description), then the composer.
 */

import { useEffect, useMemo, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useIssueThreads, useThreadMessages } from "@/lib/api/issue-threads";
import { useIssue, useIssueWatchers } from "@/lib/api/issues";
import { queryKeys } from "@/lib/api/query-keys";
import { cn } from "@/lib/utils";

import { useIssueHub } from "../hub/hub-context";
import { Composer } from "./Composer";
import { IssueOpenedEntry, isIssueOpenedEvent } from "./IssueOpened";
import { ThreadMessageItem, threadFacts } from "./ThreadMessageItem";
import { useThreadStream } from "./use-thread-stream";
import { useThreadViewer } from "./use-thread-viewer";

const PANEL = "min-w-0 rounded-[10px] border border-border bg-card";

const TAB =
  "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground";
const TAB_ON = "bg-muted font-semibold text-foreground";

interface ThreadHeadProps {
  issueId: string;
  isConnected: boolean;
}

function ThreadHead({ issueId, isConnected }: ThreadHeadProps) {
  const hub = useIssueHub();
  const threads = useIssueThreads(issueId);
  const watchers = useIssueWatchers(issueId);
  const scratchCount =
    threads.data?.items.filter((t) => t.kind === "scratch").length ?? 0;
  const watching = watchers.data ? watchers.data.items.length : null;
  const presence = [
    watching !== null ? `${watching} watching` : null,
    isConnected ? "live" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
      <div role="group" aria-label="Threads" className="flex gap-1">
        <button type="button" aria-current="true" className={cn(TAB, TAB_ON)}>
          Shared thread
        </button>
        {hub?.canWrite && (
          <button
            type="button"
            className={TAB}
            onClick={() => hub.openScratch()}
          >
            My scratch chats ({scratchCount})
          </button>
        )}
      </div>
      {presence && (
        <span className="text-xs text-muted-foreground">{presence}</span>
      )}
    </div>
  );
}

/**
 * Refresh the issue's runs when a run posts its outcome while the thread is
 * open, so the sidebar's pill turns done or failed with the thread.
 * `outcomes` is null until the thread has loaded.
 */
function useRefreshRunsOnOutcome(issueId: string, outcomes: number | null) {
  const queryClient = useQueryClient();
  const seen = useRef<number | null>(null);
  useEffect(() => {
    if (outcomes === null) return;
    if (seen.current !== null && outcomes > seen.current) {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.issues.investigationRuns(issueId),
      });
    }
    seen.current = outcomes;
  }, [queryClient, issueId, outcomes]);
}

interface ThreadViewProps {
  issueId: string;
  threadId: string;
}

function ThreadView({ issueId, threadId }: ThreadViewProps) {
  const messages = useThreadMessages(issueId, threadId);
  const { isConnected } = useThreadStream(issueId, threadId, {
    enabled: messages.isSuccess,
  });
  const viewer = useThreadViewer();
  const hub = useIssueHub();
  const issue = useIssue(issueId);
  const items = useMemo(() => messages.data ?? [], [messages.data]);
  const facts = useMemo(() => threadFacts(items), [items]);
  useRefreshRunsOnOutcome(
    issueId,
    messages.isSuccess ? facts.outcomes.size : null,
  );
  // Threads from before the opening entry existed still show who opened the
  // issue and its description, from the issue itself.
  const openerFromIssue =
    messages.isSuccess && !items.some(isIssueOpenedEvent) ? issue.data : null;

  return (
    <section aria-label="Thread" className={PANEL}>
      <ThreadHead issueId={issueId} isConnected={isConnected} />
      <div className="px-3.5 py-2">
        {messages.isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : messages.error ? (
          <p className="py-4 text-sm text-destructive">
            Couldn't load the thread: {messages.error.message}
          </p>
        ) : (
          <div className="divide-y divide-dashed divide-border">
            {openerFromIssue && (
              <IssueOpenedEntry
                issueId={issueId}
                openerId={openerFromIssue.created_by_user_id ?? null}
                sourceProvider={openerFromIssue.source_provider ?? null}
                openedAt={openerFromIssue.created_at}
                viewer={viewer}
              />
            )}
            {items.map((message) => (
              <ThreadMessageItem
                key={message.id}
                message={message}
                issueId={issueId}
                threadId={threadId}
                viewer={viewer}
                facts={facts}
              />
            ))}
            {items.length === 0 && (
              <p className="py-4 text-sm text-muted-foreground">
                No messages yet. Comment for the team, or ask the agent a
                question about this issue.
              </p>
            )}
          </div>
        )}
      </div>
      <div className="border-t border-border px-3.5 py-2.5">
        <Composer
          issueId={issueId}
          threadId={threadId}
          canAskAgent={viewer.canWrite}
          actions={
            hub?.canWrite ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={hub.isRequestingDraft}
                onClick={() => void hub.investigateFrom(threadId)}
                title="The agent drafts a brief from this thread for you to edit"
              >
                {hub.isRequestingDraft ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                Investigate…
              </Button>
            ) : null
          }
        />
      </div>
    </section>
  );
}

export function IssueThread({ issueId }: { issueId: string }) {
  const threads = useIssueThreads(issueId);
  const shared = threads.data?.items.find((t) => t.kind === "shared");

  if (threads.isLoading) {
    return (
      <section
        aria-label="Thread"
        className={cn(PANEL, "flex justify-center py-8")}
      >
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </section>
    );
  }

  if (!shared) {
    return (
      <section
        aria-label="Thread"
        className={cn(PANEL, "px-3.5 py-6 text-sm text-destructive")}
      >
        Couldn't load the thread
        {threads.error ? `: ${threads.error.message}` : "."}
      </section>
    );
  }

  return <ThreadView issueId={issueId} threadId={shared.id} />;
}
