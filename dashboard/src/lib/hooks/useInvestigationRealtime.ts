"use client";

/**
 * Hook for subscribing to real-time investigation updates.
 *
 * Automatically subscribes to the investigation channel and provides
 * parsed status updates, phase changes, and event history.
 *
 * Usage:
 *   const { status, events, isConnected } = useInvestigationRealtime(investigationId);
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useWebSocketContext } from "@/components/realtime/WebSocketProvider";

export interface InvestigationPhaseUpdate {
  phase: string;
  previousPhase?: string;
  message?: string;
  timestamp: string;
}

export interface InvestigationProgressUpdate {
  progressPct: number;
  message?: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

export interface InvestigationStatus {
  status: "queued" | "running" | "succeeded" | "failed";
  phase: string;
  progressPct: number;
  hypothesesTotal: number;
  hypothesesCompleted: number;
  currentHypothesis?: string;
  error?: string;
  rootCause?: string;
  confidence?: number;
}

export interface UseInvestigationRealtimeReturn {
  status: InvestigationStatus;
  events: InvestigationPhaseUpdate[];
  isConnected: boolean;
  lastUpdate: Date | null;
}

const INITIAL_STATUS: InvestigationStatus = {
  status: "queued",
  phase: "initializing",
  progressPct: 0,
  hypothesesTotal: 0,
  hypothesesCompleted: 0,
};

export function useInvestigationRealtime(
  investigationId: string | undefined,
  initialStatus?: Partial<InvestigationStatus>
): UseInvestigationRealtimeReturn {
  const { status: wsStatus, messages, subscribe, unsubscribe } =
    useWebSocketContext();

  const [investigationStatus, setInvestigationStatus] =
    useState<InvestigationStatus>({
      ...INITIAL_STATUS,
      ...initialStatus,
    });

  const [events, setEvents] = useState<InvestigationPhaseUpdate[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // Subscribe to investigation channel
  useEffect(() => {
    if (!investigationId) return;

    const channel = `investigation:${investigationId}`;
    subscribe(channel);

    return () => {
      unsubscribe(channel);
    };
  }, [investigationId, subscribe, unsubscribe]);

  // Process incoming messages
  useEffect(() => {
    if (!investigationId) return;

    const channel = `investigation:${investigationId}`;

    // Filter messages for this investigation
    const relevantMessages = messages.filter(
      (msg) =>
        msg.channel === channel ||
        (msg.payload as Record<string, unknown>)?.investigation_id === investigationId
    );

    if (relevantMessages.length === 0) return;

    // Process only new messages (last one since we process incrementally)
    const latestMsg = relevantMessages[relevantMessages.length - 1];
    const payload = (latestMsg.payload || {}) as Record<string, unknown>;
    const eventType = latestMsg.event_type || latestMsg.type;

    setLastUpdate(new Date());

    switch (eventType) {
      case "started":
        setInvestigationStatus((prev) => ({
          ...prev,
          status: "running",
          phase: "discovery",
          progressPct: 5,
        }));
        setEvents((prev) => [
          ...prev,
          {
            phase: "discovery",
            message: "Investigation started",
            timestamp: latestMsg.timestamp || new Date().toISOString(),
          },
        ]);
        break;

      case "phase_change":
        setInvestigationStatus((prev) => ({
          ...prev,
          phase: payload.phase as string,
        }));
        setEvents((prev) => [
          ...prev,
          {
            phase: payload.phase as string,
            previousPhase: payload.previous_phase as string,
            message: payload.message as string,
            timestamp: latestMsg.timestamp || new Date().toISOString(),
          },
        ]);
        break;

      case "progress":
        setInvestigationStatus((prev) => ({
          ...prev,
          progressPct: (payload.progress_pct as number) || prev.progressPct,
        }));
        break;

      case "hypothesis_complete":
        setInvestigationStatus((prev) => ({
          ...prev,
          hypothesesCompleted: prev.hypothesesCompleted + 1,
        }));
        break;

      case "artifact_generated":
        // Could update artifact count if tracking
        break;

      case "execution_started":
        setInvestigationStatus((prev) => ({
          ...prev,
          phase: "executing",
          currentHypothesis: payload.hypothesis_id as string,
        }));
        break;

      case "execution_completed":
        // Execution finished for a hypothesis
        break;

      case "completed":
        setInvestigationStatus((prev) => ({
          ...prev,
          status: payload.success ? "succeeded" : "failed",
          phase: "completed",
          progressPct: 100,
          rootCause: payload.root_cause as string,
          confidence: payload.confidence as number,
        }));
        setEvents((prev) => [
          ...prev,
          {
            phase: "completed",
            message: payload.summary as string || "Investigation completed",
            timestamp: latestMsg.timestamp || new Date().toISOString(),
          },
        ]);
        break;

      case "error":
        if (payload.fatal) {
          setInvestigationStatus((prev) => ({
            ...prev,
            status: "failed",
            error: payload.message as string,
          }));
        }
        setEvents((prev) => [
          ...prev,
          {
            phase: "error",
            message: payload.message as string,
            timestamp: latestMsg.timestamp || new Date().toISOString(),
          },
        ]);
        break;
    }
  }, [investigationId, messages]);

  const isConnected = wsStatus === "connected";

  return {
    status: investigationStatus,
    events,
    isConnected,
    lastUpdate,
  };
}

export default useInvestigationRealtime;
