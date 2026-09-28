/**
 * Scratch chats (spec 0001 §7.9): private chats with the agent on an issue.
 * Only the owner sees them. Selected messages can be published to the shared
 * thread, and "Investigate from here" drafts a brief from the chat.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Search,
  Share2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/error-message";
import {
  useCreateScratchThread,
  useDeleteThread,
  useIssueThreads,
  usePublishFromScratch,
  useRenameThread,
  useThreadMessages,
  type IssueThread,
  type ThreadMessage,
} from "@/lib/api/issue-threads";
import { formatDate } from "@/lib/utils";

import { Composer } from "../thread/Composer";
import { Pill } from "../thread/Pill";
import { ThreadMessageItem, threadFacts } from "../thread/ThreadMessageItem";
import { useThreadStream } from "../thread/use-thread-stream";
import { useThreadViewer } from "../thread/use-thread-viewer";

export function scratchTitle(thread: Pick<IssueThread, "title">): string {
  return thread.title?.trim() || "Untitled scratch chat";
}

/** Messages worth publishing: finished, not deleted, with something to say. */
function publishable(message: ThreadMessage): boolean {
  return (
    message.deleted_at === null &&
    (message.kind === "comment" || message.kind === "agent_reply") &&
    message.status !== "queued" &&
    message.status !== "streaming"
  );
}

// ----------------------------------------------------------------------------
// The list of chats
// ----------------------------------------------------------------------------

function ChatList({
  issueId,
  chats,
  loading,
  onOpen,
}: {
  issueId: string;
  chats: IssueThread[];
  loading: boolean;
  onOpen: (threadId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const create = useCreateScratchThread(issueId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const thread = await create.mutateAsync(title.trim() || null);
      setTitle("");
      onOpen(thread.id);
    } catch (error) {
      toast.error("Couldn't create the scratch chat", {
        description: errorText(error),
      });
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <form className="flex gap-2" onSubmit={submit}>
        <Input
          aria-label="New chat title"
          value={title}
          maxLength={200}
          autoFocus
          placeholder="What are you exploring? (optional)"
          onChange={(e) => setTitle(e.target.value)}
        />
        <Button type="submit" disabled={create.isPending} className="gap-1">
          {create.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          New chat
        </Button>
      </form>

      {loading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : chats.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">
          No scratch chats yet. Start one to ask the agent something without
          posting to the shared thread.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-border" aria-label="Scratch chats">
          {chats.map((chat) => (
            <li key={chat.id}>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm hover:text-primary"
                onClick={() => onOpen(chat.id)}
              >
                <span className="truncate font-medium">
                  {scratchTitle(chat)}
                </span>
                <span className="flex-none text-xs text-muted-foreground">
                  {formatDate(chat.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// One chat
// ----------------------------------------------------------------------------

function ChatHeader({
  issueId,
  chat,
  onBack,
  onDeleted,
}: {
  issueId: string;
  chat: IssueThread;
  onBack: () => void;
  onDeleted: () => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(chat.title ?? "");
  const rename = useRenameThread(issueId);
  const remove = useDeleteThread(issueId);

  const saveTitle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await rename.mutateAsync({ threadId: chat.id, title: title.trim() });
      setRenaming(false);
    } catch (error) {
      toast.error("Couldn't rename the scratch chat", {
        description: errorText(error),
      });
    }
  };

  const onDelete = async () => {
    if (
      !window.confirm(`Delete "${scratchTitle(chat)}"? This can't be undone.`)
    )
      return;
    try {
      await remove.mutateAsync(chat.id);
      toast.success("Scratch chat deleted");
      onDeleted();
    } catch (error) {
      toast.error("Couldn't delete the scratch chat", {
        description: errorText(error),
      });
    }
  };

  return (
    <div className="border-b px-5 pb-3 pt-4">
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2 mb-1 h-7 gap-1 px-2 text-xs text-muted-foreground"
        onClick={onBack}
      >
        <ArrowLeft className="h-3 w-3" />
        All scratch chats
      </Button>
      {renaming ? (
        <form className="flex gap-2" onSubmit={saveTitle}>
          <SheetTitle className="sr-only">Rename scratch chat</SheetTitle>
          <Input
            aria-label="Chat title"
            value={title}
            maxLength={200}
            autoFocus
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button
            type="submit"
            size="sm"
            disabled={!title.trim() || rename.isPending}
          >
            Save
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setRenaming(false)}
          >
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex items-center gap-2 pr-6">
          <SheetTitle className="truncate text-base">
            Scratch: {scratchTitle(chat)}
          </SheetTitle>
          <Pill>
            <Lock className="h-3 w-3" />
            private
          </Pill>
          <div className="ml-auto flex">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Rename chat"
              onClick={() => {
                setTitle(chat.title ?? "");
                setRenaming(true);
              }}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Delete chat"
              disabled={remove.isPending}
              onClick={() => void onDelete()}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
      <SheetDescription className="mt-1 text-xs">
        Only you can see this chat. Queries still run as you and are audited.
      </SheetDescription>
    </div>
  );
}

function ChatPanel({
  issueId,
  chat,
  onBack,
  onInvestigate,
  isRequestingDraft,
}: {
  issueId: string;
  chat: IssueThread;
  onBack: () => void;
  onInvestigate: (threadId: string) => void;
  isRequestingDraft: boolean;
}) {
  const messages = useThreadMessages(issueId, chat.id);
  useThreadStream(issueId, chat.id, { enabled: messages.isSuccess });
  const viewer = useThreadViewer();
  const facts = useMemo(
    () => threadFacts(messages.data ?? []),
    [messages.data],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [publishing, setPublishing] = useState(false);
  const [note, setNote] = useState("");
  const publish = usePublishFromScratch(issueId);

  // Drop selections of messages that went away or can't be published.
  const items = messages.data ?? [];
  const selectedIds = items
    .filter((m) => selected.has(m.id) && publishable(m))
    .map((m) => m.id);

  const toggle = (id: string, on: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const doPublish = async () => {
    try {
      await publish.mutateAsync({
        threadId: chat.id,
        body: { message_ids: selectedIds, note: note.trim() || null },
      });
      toast.success("Published to the shared thread");
      setSelected(new Set());
      setNote("");
      setPublishing(false);
    } catch (error) {
      toast.error("Couldn't publish", { description: errorText(error) });
    }
  };

  return (
    <>
      <ChatHeader
        issueId={issueId}
        chat={chat}
        onBack={onBack}
        onDeleted={onBack}
      />
      <div className="flex-1 overflow-y-auto px-5 py-2">
        {messages.isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : messages.error ? (
          <p className="py-4 text-sm text-destructive">
            Couldn't load the chat: {messages.error.message}
          </p>
        ) : items.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            Ask the agent anything about this issue. Nothing here is shared
            until you publish it.
          </p>
        ) : (
          <ul className="divide-y divide-dashed divide-border">
            {items.map((message) => (
              <li key={message.id} className="flex items-start gap-2">
                {publishable(message) ? (
                  <input
                    type="checkbox"
                    className="mt-4 h-4 w-4 flex-none accent-primary"
                    aria-label={`Select message ${message.seq}`}
                    checked={selected.has(message.id)}
                    onChange={(e) => toggle(message.id, e.target.checked)}
                  />
                ) : (
                  <span className="w-4 flex-none" />
                )}
                <div className="min-w-0 flex-1">
                  <ThreadMessageItem
                    message={message}
                    issueId={issueId}
                    threadId={chat.id}
                    viewer={viewer}
                    facts={facts}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-3 border-t px-5 py-3">
        <Composer
          issueId={issueId}
          threadId={chat.id}
          canAskAgent={viewer.canWrite}
          privateChat
        />
        {publishing ? (
          <div
            role="group"
            aria-label="Publish to the shared thread"
            className="space-y-2 rounded-md border border-border bg-muted/40 p-2.5"
          >
            <p className="text-xs text-muted-foreground">
              {selectedIds.length} message
              {selectedIds.length === 1 ? "" : "s"} and their query results are
              copied to the shared thread, where everyone on the issue sees
              them.
            </p>
            <Textarea
              aria-label="Note for the team"
              value={note}
              rows={2}
              maxLength={2000}
              placeholder="Why this matters (optional)"
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                className="h-7 text-xs"
                disabled={publish.isPending || selectedIds.length === 0}
                onClick={() => void doPublish()}
              >
                {publish.isPending && (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                )}
                Publish
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setPublishing(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              disabled={selectedIds.length === 0}
              onClick={() => setPublishing(true)}
            >
              <Share2 className="h-3.5 w-3.5" />
              Publish selected ({selectedIds.length})
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              disabled={isRequestingDraft}
              onClick={() => onInvestigate(chat.id)}
            >
              {isRequestingDraft ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Search className="h-3.5 w-3.5" />
              )}
              Investigate from here
            </Button>
          </div>
        )}
      </div>
    </>
  );
}

// ----------------------------------------------------------------------------
// The drawer
// ----------------------------------------------------------------------------

export interface ScratchDrawerProps {
  issueId: string;
  open: boolean;
  /** The open chat, or null for the list. */
  threadId: string | null;
  onSelect: (threadId: string | null) => void;
  onClose: () => void;
  onInvestigate: (threadId: string) => void;
  isRequestingDraft: boolean;
}

export function ScratchDrawer({
  issueId,
  open,
  threadId,
  onSelect,
  onClose,
  onInvestigate,
  isRequestingDraft,
}: ScratchDrawerProps) {
  const threads = useIssueThreads(issueId);
  const chats = (threads.data?.items ?? []).filter((t) => t.kind === "scratch");
  const chat = threadId ? chats.find((t) => t.id === threadId) : undefined;

  // A chat deleted elsewhere (or not loaded yet) falls back to the list.
  useEffect(() => {
    if (open && threadId && threads.isSuccess && !chat) onSelect(null);
  }, [open, threadId, threads.isSuccess, chat, onSelect]);

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-md"
      >
        {chat ? (
          <ChatPanel
            key={chat.id}
            issueId={issueId}
            chat={chat}
            onBack={() => onSelect(null)}
            onInvestigate={onInvestigate}
            isRequestingDraft={isRequestingDraft}
          />
        ) : (
          <>
            <div className="border-b px-5 pb-3 pt-4">
              <SheetTitle className="flex items-center gap-2 text-base">
                <Lock className="h-4 w-4" />
                My scratch chats
              </SheetTitle>
              <SheetDescription className="mt-1 text-xs">
                Private chats with the agent about this issue. Publish what's
                useful to the shared thread.
              </SheetDescription>
            </div>
            <ChatList
              issueId={issueId}
              chats={chats}
              loading={threads.isLoading}
              onOpen={onSelect}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
