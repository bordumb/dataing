/**
 * Live updates for an issue thread over Server-Sent Events.
 *
 * Every `message` event carries a full message row; the same id arrives again
 * with a higher rev as an agent reply streams. Rows are merged into the React
 * Query cache by (id, rev), batched per animation frame so a fast token stream
 * re-renders at most once a frame. Reconnects resume from the highest rev seen
 * with exponential backoff, following lib/notifications/context.tsx.
 */

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useJwtAuth } from "@/lib/auth/jwt-context";
import {
  maxRev,
  mergeIntoCache,
  threadStreamUrl,
  type ThreadMessage,
} from "@/lib/api/issue-threads";
import { queryKeys } from "@/lib/api/query-keys";

const MAX_BACKOFF_MS = 30_000;

function scheduleFrame(callback: () => void): () => void {
  if (typeof window.requestAnimationFrame === "function") {
    const handle = window.requestAnimationFrame(callback);
    return () => window.cancelAnimationFrame(handle);
  }
  const handle = window.setTimeout(callback, 16);
  return () => window.clearTimeout(handle);
}

interface ThreadStreamOptions {
  /** Connect only once the initial page of messages is in the cache. */
  enabled: boolean;
}

export function useThreadStream(
  issueId: string,
  threadId: string | null,
  { enabled }: ThreadStreamOptions,
): { isConnected: boolean } {
  const queryClient = useQueryClient();
  const { accessToken } = useJwtAuth();
  const [isConnected, setIsConnected] = React.useState(false);

  React.useEffect(() => {
    if (!enabled || !threadId) {
      setIsConnected(false);
      return;
    }

    const key = queryKeys.issueThreads.messages(issueId, threadId);
    let source: EventSource | null = null;
    let retryCount = 0;
    let retryTimer: number | null = null;
    let pending: ThreadMessage[] = [];
    let cancelFrame: (() => void) | null = null;
    let closed = false;
    let lastRev = maxRev(queryClient.getQueryData<ThreadMessage[]>(key));

    const flush = () => {
      cancelFrame = null;
      const batch = pending;
      pending = [];
      mergeIntoCache(queryClient, issueId, threadId, batch);
    };

    const onMessage = (event: MessageEvent<string>) => {
      let message: ThreadMessage;
      try {
        message = JSON.parse(event.data) as ThreadMessage;
      } catch {
        return;
      }
      lastRev = Math.max(lastRev, message.rev);
      pending.push(message);
      if (!cancelFrame) cancelFrame = scheduleFrame(flush);
    };

    const connect = () => {
      retryTimer = null;
      if (closed) return;
      // Resume after everything already merged or waiting to be merged.
      lastRev = Math.max(
        lastRev,
        maxRev(queryClient.getQueryData<ThreadMessage[]>(key)),
      );
      const es = new EventSource(
        threadStreamUrl(issueId, threadId, lastRev, accessToken),
      );
      source = es;

      es.onopen = () => {
        retryCount = 0;
        setIsConnected(true);
      };
      es.addEventListener("message", onMessage as EventListener);
      es.addEventListener("heartbeat", () => setIsConnected(true));
      // The server ends long-lived streams; pick up where we left off.
      es.addEventListener("timeout", () => {
        es.close();
        source = null;
        retryCount = 0;
        connect();
      });
      es.onerror = () => {
        setIsConnected(false);
        es.close();
        source = null;
        if (closed) return;
        const delay = Math.min(
          1000 * Math.pow(2, retryCount) + Math.random() * 1000,
          MAX_BACKOFF_MS,
        );
        retryCount++;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closed = true;
      source?.close();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      cancelFrame?.();
      if (pending.length > 0) flush();
      setIsConnected(false);
    };
  }, [enabled, issueId, threadId, accessToken, queryClient]);

  return { isConnected };
}
