/**
 * Message component for assistant chat.
 *
 * Renders user and assistant messages with markdown support.
 */

import { useState } from "react";
import { User, Bot, Wrench, Loader2, ThumbsUp, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { useSubmitFeedback } from "@/lib/api/investigation-feedback";
import type { AssistantMessage as AssistantMessageType } from "./useAssistant";

interface AssistantMessageProps {
  message: AssistantMessageType;
  sessionInvestigationId?: string;
}

export function AssistantMessage({
  message,
  sessionInvestigationId,
}: AssistantMessageProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isTool = message.role === "tool";

  const [isMarkedHelpful, setIsMarkedHelpful] = useState(false);
  const submitFeedback = useSubmitFeedback();

  const handleMarkHelpful = () => {
    submitFeedback.mutate(
      {
        target_type: "assistant_message",
        target_id: message.id,
        investigation_id: sessionInvestigationId,
        rating: 1,
      },
      {
        onSuccess: () => {
          setIsMarkedHelpful(true);
        },
      },
    );
  };

  return (
    <div
      className={cn(
        "flex gap-3 p-4 rounded-lg",
        isUser && "bg-muted/50",
        isAssistant && "bg-background",
        isTool && "bg-yellow-50 dark:bg-yellow-950/20",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser && "bg-primary text-primary-foreground",
          isAssistant && "bg-secondary text-secondary-foreground",
          isTool && "bg-yellow-500 text-white",
        )}
      >
        {isUser && <User className="h-4 w-4" />}
        {isAssistant && <Bot className="h-4 w-4" />}
        {isTool && <Wrench className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="flex-1 space-y-2 overflow-hidden">
        {/* Role label */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {isUser && "You"}
            {isAssistant && "Assistant"}
            {isTool && "Tool"}
          </span>
          {message.isStreaming && (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          )}
        </div>

        {/* Message content */}
        <div className="text-sm whitespace-pre-wrap break-words">
          {message.content || (message.isStreaming && "...")}
        </div>

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-2 space-y-1">
            {message.toolCalls.map((tool, index) => (
              <div
                key={index}
                className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded px-2 py-1"
              >
                <Wrench className="h-3 w-3" />
                <span className="font-mono">{tool.name}</span>
              </div>
            ))}
          </div>
        )}

        {/* Mark as helpful button (assistant messages only, when not streaming) */}
        {isAssistant && !message.isStreaming && message.content && (
          <div className="mt-2 pt-2 border-t border-border/50">
            {isMarkedHelpful ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <Check className="h-3 w-3" />
                Marked as helpful
              </span>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                onClick={handleMarkHelpful}
                disabled={submitFeedback.isPending}
              >
                {submitFeedback.isPending ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <ThumbsUp className="h-3 w-3 mr-1" />
                )}
                This was helpful
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
