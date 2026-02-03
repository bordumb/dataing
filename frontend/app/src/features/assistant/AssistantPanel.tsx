/**
 * Chat panel component for the assistant widget.
 *
 * Contains message history, input field, and streaming indicators.
 */

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Plus, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { AssistantMessage } from "./AssistantMessage";
import { useAssistant } from "./useAssistant";

// Example placeholder questions
const PLACEHOLDER_QUESTIONS = [
  "Why is my container unhealthy?",
  "What caused the null spike in orders?",
  "Show me recent errors in the logs",
  "Explain the schema for customers table",
];

export function AssistantPanel() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    session,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    createSession,
    clearSession,
  } = useAssistant({
    onError: (err) => console.error("Assistant error:", err),
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-create session if none exists
  useEffect(() => {
    if (!session && !isLoading) {
      createSession();
    }
  }, [session, isLoading, createSession]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isStreaming) return;

    const message = input;
    setInput("");
    await sendMessage(message);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
  };

  const handleQuickQuestion = (question: string) => {
    setInput(question);
    textareaRef.current?.focus();
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Empty state */}
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center p-4">
            <div className="text-muted-foreground mb-4">
              <p className="text-sm font-medium">How can I help you today?</p>
              <p className="text-xs mt-1">
                Ask about infrastructure, data issues, or investigations.
              </p>
            </div>

            {/* Quick questions */}
            <div className="space-y-2 w-full max-w-sm">
              {PLACEHOLDER_QUESTIONS.map((question, index) => (
                <button
                  key={index}
                  onClick={() => handleQuickQuestion(question)}
                  className="w-full text-left text-xs p-2 rounded-md border hover:bg-muted transition-colors"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading state */}
        {isLoading && messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Messages */}
        {messages.map((message) => (
          <AssistantMessage
            key={message.id}
            message={message}
            sessionInvestigationId={session?.investigationId}
          />
        ))}

        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-2 p-2 rounded-md bg-destructive/10 text-destructive flex items-center gap-2 text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2"
            onClick={clearSession}
          >
            New Chat
          </Button>
        </div>
      )}

      {/* Input area */}
      <div className="border-t p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="flex-1 relative">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              className="min-h-[40px] max-h-[150px] resize-none pr-10"
              disabled={isStreaming || isLoading}
            />
          </div>
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim() || isStreaming || isLoading}
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>

        {/* New chat button */}
        <div className="flex justify-end mt-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={clearSession}
            disabled={isStreaming}
            className="text-xs text-muted-foreground"
          >
            <Plus className="h-3 w-3 mr-1" />
            New Chat
          </Button>
        </div>
      </div>
    </div>
  );
}
