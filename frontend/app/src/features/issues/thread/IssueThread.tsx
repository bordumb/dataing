/**
 * The issue's shared thread: comments, agent answers and events, live.
 */

import { Loader2, MessageSquare } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useIssueThreads, useThreadMessages } from "@/lib/api/issue-threads";
import { useUserDirectory } from "@/lib/api/users";
import { useJwtAuth } from "@/lib/auth/jwt-context";
import { useRole } from "@/lib/auth/use-role";

import { Composer } from "./Composer";
import { ThreadMessageItem, type ThreadViewer } from "./ThreadMessageItem";
import { useThreadStream } from "./use-thread-stream";

interface ThreadViewProps {
  issueId: string;
  threadId: string;
}

function ThreadView({ issueId, threadId }: ThreadViewProps) {
  const messages = useThreadMessages(issueId, threadId);
  const { isConnected } = useThreadStream(issueId, threadId, {
    enabled: messages.isSuccess,
  });
  const { user } = useJwtAuth();
  const { isMember, isAdmin } = useRole();
  const { nameOf } = useUserDirectory();

  const viewer: ThreadViewer = {
    userId: user?.id ?? null,
    isAdmin,
    nameOf: (id) =>
      id && id === user?.id && user.name ? user.name : nameOf(id),
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 border-b pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          Thread
        </CardTitle>
        {isConnected && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            live
          </span>
        )}
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
              />
            ))}
          </div>
        )}
        <div className="border-t pt-3">
          <Composer
            issueId={issueId}
            threadId={threadId}
            canAskAgent={isMember}
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
