/**
 * The sidebar's list of the person's own scratch chats on the issue, with
 * "＋ New scratch chat" (the mockup's last sidebar section).
 */

import { Button } from "@/components/ui/Button";
import { useIssueThreads } from "@/lib/api/issue-threads";

import { useIssueHub } from "../hub/hub-context";
import { SectionTitle } from "../SectionTitle";
import { LINK_CLASS, formatTime } from "../thread/message-parts";
import { scratchTitle } from "./ScratchDrawer";

export function ScratchChatsSection({ issueId }: { issueId: string }) {
  const hub = useIssueHub();
  const threads = useIssueThreads(issueId);
  if (!hub?.canWrite) return null;
  const chats = (threads.data?.items ?? []).filter((t) => t.kind === "scratch");

  return (
    <div>
      <SectionTitle>Your scratch chats</SectionTitle>
      {chats.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Explore privately with the agent, then publish what helps.
        </p>
      ) : (
        <ul aria-label="Your scratch chats">
          {chats.map((chat) => (
            <li
              key={chat.id}
              className="flex min-h-7 items-center justify-between gap-2 text-sm"
            >
              <button
                type="button"
                className={`truncate text-left ${LINK_CLASS}`}
                onClick={() => hub.openScratch(chat.id)}
              >
                {scratchTitle(chat)}
              </button>
              <span className="flex-none text-xs text-muted-foreground">
                {formatTime(chat.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Button
        variant="outline"
        size="sm"
        className="mt-1.5 h-8 w-full gap-1 text-xs"
        onClick={() => hub.openScratch()}
      >
        <span aria-hidden>＋</span>
        New scratch chat
      </Button>
    </div>
  );
}
