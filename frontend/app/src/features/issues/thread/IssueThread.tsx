/**
 * The issue's shared thread: comments, agent answers and events, live.
 */

import { useMemo } from "react";
import { Loader2, Lock, MessageSquare, Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useIssueThreads, useThreadMessages } from "@/lib/api/issue-threads";

import { useIssueHub } from "../hub/hub-context";
import { Composer } from "./Composer";
import { ThreadMessageItem, threadFacts } from "./ThreadMessageItem";
import { useThreadStream } from "./use-thread-stream";
import { useThreadViewer } from "./use-thread-viewer";

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
  const threads = useIssueThreads(issueId);
  const scratchCount =
    threads.data?.items.filter((t) => t.kind === "scratch").length ?? 0;
  const facts = useMemo(
    () => threadFacts(messages.data ?? []),
    [messages.data],
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 border-b pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          Thread
        </CardTitle>
        <div className="flex items-center gap-3">
          {hub?.canWrite && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs text-muted-foreground"
              onClick={() => hub.openScratch()}
            >
              <Lock className="h-3 w-3" />
              My scratch chats{scratchCount > 0 ? ` (${scratchCount})` : ""}
            </Button>
          )}
          {isConnected && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              live
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {messages.isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : messages.error ? (
          <p className="py-4 text-sm text-destructive">
            Couldn't load the thread: {messages.error.message}
          </p>
        ) : (messages.data ?? []).length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            No messages yet. Comment for the team, or ask the agent a question
            about this issue.
          </p>
        ) : (
          <div className="divide-y divide-dashed divide-border">
            {(messages.data ?? []).map((message) => (
              <ThreadMessageItem
                key={message.id}
                message={message}
                issueId={issueId}
                threadId={threadId}
                viewer={viewer}
                facts={facts}
              />
            ))}
          </div>
        )}
        <div className="border-t pt-3">
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
      </CardContent>
    </Card>
  );
}

export function IssueThread({ issueId }: { issueId: string }) {
  const threads = useIssueThreads(issueId);
  const shared = threads.data?.items.find((t) => t.kind === "shared");

  if (threads.isLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!shared) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-destructive">
          Couldn't load the thread
          {threads.error ? `: ${threads.error.message}` : "."}
        </CardContent>
      </Card>
    );
  }

  return <ThreadView issueId={issueId} threadId={shared.id} />;
}
