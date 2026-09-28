/**
 * The sidebar's list of the person's own scratch chats on the issue.
 */

import { Lock, Plus } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useIssueThreads } from "@/lib/api/issue-threads";
import { formatDate } from "@/lib/utils";

import { useIssueHub } from "../hub/hub-context";
import { scratchTitle } from "./ScratchDrawer";

export function ScratchChatsSection({ issueId }: { issueId: string }) {
  const hub = useIssueHub();
  const threads = useIssueThreads(issueId);
  if (!hub?.canWrite) return null;
  const chats = (threads.data?.items ?? []).filter((t) => t.kind === "scratch");

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Lock className="h-4 w-4" />
          Your scratch chats
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {chats.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Explore privately with the agent, then publish what helps.
          </p>
        ) : (
          <ul aria-label="Your scratch chats">
            {chats.map((chat) => (
              <li
                key={chat.id}
                className="flex items-center justify-between gap-2 py-1 text-sm"
              >
                <button
                  type="button"
                  className="truncate text-left text-primary hover:underline"
                  onClick={() => hub.openScratch(chat.id)}
                >
                  {scratchTitle(chat)}
                </button>
                <span className="flex-none text-xs text-muted-foreground">
                  {formatDate(chat.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Button
          variant="outline"
          size="sm"
          className="mt-2 w-full gap-1"
          onClick={() => hub.openScratch()}
        >
          <Plus className="h-3.5 w-3.5" />
          New scratch chat
        </Button>
      </CardContent>
    </Card>
  );
}
