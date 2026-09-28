/**
 * Thread composer: write a comment for the team, or ask the agent.
 *
 * Asking the agent runs read-only queries as the asker, so it needs the write
 * scope; viewers see the option disabled with the reason.
 */

import { useState } from "react";
import { Bot, Loader2, MessageSquare, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { usePostMessage } from "@/lib/api/issue-threads";
import { errorText } from "@/lib/api/error-message";
import { cn } from "@/lib/utils";

type Mode = "comment" | "ask";

export const ASK_AGENT_VIEWER_REASON =
  "Viewers can comment but can't ask the agent: it runs queries, which needs member access.";

const PLACEHOLDER: Record<Mode, string> = {
  comment: "Write a comment for the team (Markdown)",
  ask: "Ask the agent. It runs read-only queries as you.",
};

const HINT: Record<Mode, string> = {
  comment: "Comments are visible to everyone on this issue.",
  ask: "Agent replies are visible to everyone on this issue.",
};

const PRIVATE_PLACEHOLDER: Record<Mode, string> = {
  comment: "A note to yourself (Markdown)",
  ask: "Ask the agent privately…",
};

const PRIVATE_HINT: Record<Mode, string> = {
  comment: "Only you can see this chat.",
  ask: "Only you can see this chat. Queries still run as you and are audited.",
};

interface ComposerProps {
  issueId: string;
  threadId: string;
  canAskAgent: boolean;
  /** Extra buttons beside Send, such as Investigate…. */
  actions?: React.ReactNode;
  /** A scratch chat: asks the agent by default, and says only you see it. */
  privateChat?: boolean;
}

export function Composer({
  issueId,
  threadId,
  canAskAgent,
  actions,
  privateChat = false,
}: ComposerProps) {
  const [mode, setMode] = useState<Mode>(privateChat ? "ask" : "comment");
  const placeholder = privateChat ? PRIVATE_PLACEHOLDER : PLACEHOLDER;
  const hint = privateChat ? PRIVATE_HINT : HINT;
  const [body, setBody] = useState("");
  const post = usePostMessage(issueId, threadId);
  const effectiveMode: Mode = canAskAgent ? mode : "comment";
  const canSend = body.trim().length > 0 && !post.isPending;

  const send = async () => {
    if (!canSend) return;
    try {
      await post.mutateAsync({
        body_md: body.trim(),
        ask_agent: effectiveMode === "ask",
      });
      setBody("");
    } catch (error) {
      toast.error(
        effectiveMode === "ask"
          ? "Couldn't ask the agent"
          : "Couldn't post the comment",
        { description: errorText(error) },
      );
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void send();
    }
  };

  const modeButton = (value: Mode, label: string, Icon: typeof Bot) => {
    const disabled = value === "ask" && !canAskAgent;
    return (
      <button
        type="button"
        aria-pressed={effectiveMode === value}
        disabled={disabled}
        title={disabled ? ASK_AGENT_VIEWER_REASON : undefined}
        onClick={() => setMode(value)}
        className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1 text-xs text-muted-foreground transition-colors",
          effectiveMode === value && "bg-muted font-semibold text-foreground",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <Icon className="h-3.5 w-3.5" />
        {label}
      </button>
    );
  };

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <div
        role="group"
        aria-label="Message type"
        className="inline-flex overflow-hidden rounded-md border border-border"
      >
        {modeButton("comment", "Comment", MessageSquare)}
        {modeButton("ask", "Ask agent", Bot)}
      </div>
      {!canAskAgent && (
        <p className="text-xs text-muted-foreground">
          {ASK_AGENT_VIEWER_REASON}
        </p>
      )}
      <Textarea
        aria-label={effectiveMode === "ask" ? "Question" : "Comment"}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder[effectiveMode]}
        disabled={post.isPending}
        rows={3}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p
          className={cn(
            "text-xs",
            effectiveMode === "ask" && !privateChat
              ? "text-amber-700 dark:text-amber-400"
              : "text-muted-foreground",
          )}
        >
          {hint[effectiveMode]}
        </p>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-muted-foreground sm:inline">
            ⌘/Ctrl+Enter
          </span>
          {actions}
          <Button
            type="submit"
            size="sm"
            disabled={!canSend}
            className="gap-1.5"
          >
            {post.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : effectiveMode === "ask" ? (
              <Bot className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Send
          </Button>
        </div>
      </div>
    </form>
  );
}
