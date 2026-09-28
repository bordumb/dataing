import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import {
  useInvestigation,
  subscribeToInvestigation,
} from "@/lib/api/investigations";
import { useCancelInvestigationApiV1InvestigationsInvestigationIdCancelPost } from "@/lib/api/generated/investigations/investigations";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  ArrowLeft,
  RefreshCw,
  Bot,
  Loader2,
  Share2,
  ChevronDown,
  XCircle,
} from "lucide-react";

import {
  StepTimeline,
  PatternList,
  EvidenceList,
  CodifyWidget,
} from "./components";
import { InvestigationFeedbackProvider } from "./context/InvestigationFeedbackContext";
import { InvestigationFeedbackButtons } from "./components/InvestigationFeedbackButtons";
import { useRole } from "@/lib/auth";

function getStatusVariant(status: string) {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "destructive";
    case "active":
      return "warning";
    case "cancelled":
    case "inconclusive":
    case "suspended":
      return "secondary";
    default:
      return "outline";
  }
}

interface ShareMenuProps {
  isOpen: boolean;
  onClose: () => void;
}

function ShareMenu({ isOpen, onClose }: ShareMenuProps) {
  if (!isOpen) return null;

  const mockUsers = [
    { id: "1", name: "Alice Chen", email: "alice@example.com" },
    { id: "2", name: "Bob Smith", email: "bob@example.com" },
    { id: "3", name: "Carol Jones", email: "carol@example.com" },
  ];

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute right-0 top-full mt-2 w-72 bg-popover border rounded-lg shadow-lg z-50 p-3">
        <p className="text-sm font-medium mb-2">Share investigation</p>
        <div className="space-y-2">
          {mockUsers.map((user) => (
            <button
              key={user.id}
              className="w-full flex items-center gap-3 p-2 rounded hover:bg-muted text-left transition-colors"
              onClick={() => {
                alert(`Shared with ${user.name} (mock)`);
                onClose();
              }}
            >
              <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium text-sm">
                {user.name.charAt(0)}
              </div>
              <div>
                <p className="text-sm font-medium">{user.name}</p>
                <p className="text-xs text-muted-foreground">{user.email}</p>
              </div>
            </button>
          ))}
        </div>
        <div className="border-t mt-3 pt-3">
          <button
            className="w-full text-sm text-primary hover:underline"
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              alert("Link copied to clipboard!");
              onClose();
            }}
          >
            Copy shareable link
          </button>
        </div>
      </div>
    </>
  );
}

interface SynthesisData {
  confidence?: number;
  root_cause?: string | null;
  summary?: string;
  recommendations?: string[];
  supporting_evidence?: string[];
  causal_chain?: string[];
  estimated_onset?: string;
  affected_scope?: string;
}

function SynthesisCard({
  synthesis,
  investigationId,
}: {
  synthesis: unknown;
  investigationId: string;
}) {
  // Handle non-object synthesis
  if (typeof synthesis !== "object" || synthesis === null) {
    return (
      <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
        <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">
          Root Cause Analysis
        </p>
        <p className="text-sm text-green-700 dark:text-green-300 leading-relaxed">
          {String(synthesis)}
        </p>
      </div>
    );
  }

  const syn = synthesis as SynthesisData;
  const hasRootCause = syn.root_cause && typeof syn.root_cause === "string";
  const hasSummary = syn.summary && typeof syn.summary === "string";
  const hasRecommendations =
    Array.isArray(syn.recommendations) && syn.recommendations.length > 0;
  const hasEvidence =
    Array.isArray(syn.supporting_evidence) &&
    syn.supporting_evidence.length > 0;
  const hasCausalChain =
    Array.isArray(syn.causal_chain) && syn.causal_chain.length > 0;
  const hasOnset =
    syn.estimated_onset && typeof syn.estimated_onset === "string";
  const hasScope = syn.affected_scope && typeof syn.affected_scope === "string";
  const confidence = typeof syn.confidence === "number" ? syn.confidence : null;

  return (
    <div className="space-y-4">
      {/* Root Cause / Summary */}
      {(hasRootCause || hasSummary) && (
        <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-green-800 dark:text-green-200">
              Root Cause Analysis
            </p>
            <div className="flex items-center gap-2">
              {confidence !== null && (
                <Badge variant="outline" className="text-xs">
                  {Math.round(confidence * 100)}% confidence
                </Badge>
              )}
              <InvestigationFeedbackButtons
                targetType="synthesis"
                targetId={investigationId}
              />
            </div>
          </div>
          <p className="text-sm text-green-700 dark:text-green-300 leading-relaxed">
            {hasRootCause ? syn.root_cause : syn.summary}
          </p>
        </div>
      )}

      {/* No root cause determined */}
      {!hasRootCause && !hasSummary && (
        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
              Analysis Complete
            </p>
            <div className="flex items-center gap-2">
              {confidence !== null && (
                <Badge variant="outline" className="text-xs">
                  {Math.round(confidence * 100)}% confidence
                </Badge>
              )}
              <InvestigationFeedbackButtons
                targetType="synthesis"
                targetId={investigationId}
              />
            </div>
          </div>
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            Unable to determine a definitive root cause. See supporting evidence
            and recommendations below.
          </p>
        </div>
      )}

      {/* Causal Chain */}
      {hasCausalChain && (
        <div className="p-4 bg-muted/30 rounded-lg border">
          <p className="text-sm font-medium mb-3">Causal Chain</p>
          <div className="flex flex-wrap items-center gap-2">
            {syn.causal_chain!.map((step, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="px-3 py-1.5 bg-background rounded border text-sm">
                  {step}
                </span>
                {i < syn.causal_chain!.length - 1 && (
                  <span className="text-muted-foreground">→</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeline & Scope */}
      {(hasOnset || hasScope) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {hasOnset && (
            <div className="p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
              <p className="text-xs font-medium text-orange-800 dark:text-orange-200 uppercase tracking-wide mb-1">
                Estimated Onset
              </p>
              <p className="text-sm text-orange-700 dark:text-orange-300">
                {syn.estimated_onset}
              </p>
            </div>
          )}
          {hasScope && (
            <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800">
              <p className="text-xs font-medium text-purple-800 dark:text-purple-200 uppercase tracking-wide mb-1">
                Affected Scope
              </p>
              <p className="text-sm text-purple-700 dark:text-purple-300">
                {syn.affected_scope}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Recommendations */}
      {hasRecommendations && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <p className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-3">
            Recommendations
          </p>
          <ul className="space-y-3">
            {syn.recommendations!.map((rec, i) => (
              <li key={i} className="flex items-start justify-between gap-2">
                <div className="flex gap-2 text-sm text-blue-700 dark:text-blue-300">
                  <span className="shrink-0">•</span>
                  <span>{rec}</span>
                </div>
                <InvestigationFeedbackButtons
                  targetType="recommendation"
                  targetId={`${investigationId}-rec-${i}`}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Supporting Evidence */}
      {hasEvidence && (
        <div className="p-4 bg-muted/50 rounded-lg border">
          <p className="text-sm font-medium mb-3">Supporting Evidence</p>
          <div className="space-y-3">
            {syn.supporting_evidence!.map((evidence, i) => (
              <div
                key={i}
                className="p-3 bg-background rounded border text-sm leading-relaxed"
              >
                {evidence}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error, refetch } = useInvestigation(id);
  const { isMember } = useRole();
  const cancelMutation =
    useCancelInvestigationApiV1InvestigationsInvestigationIdCancelPost();
  const [sseStatus, setSseStatus] = useState<
    "connecting" | "connected" | "error"
  >("connecting");
  const sseCleanupRef = useRef<(() => void) | null>(null);
  const [showShareMenu, setShowShareMenu] = useState(false);

  // Subscribe to SSE updates
  useEffect(() => {
    if (!id || !data) return;

    // Clean up previous subscription
    if (sseCleanupRef.current) {
      sseCleanupRef.current();
    }

    const cleanup = subscribeToInvestigation(id, {
      onStepChanged: () => {
        refetch();
      },
      onStatusChanged: () => {
        refetch();
      },
      onEnded: () => {
        refetch();
        setSseStatus("connected");
      },
      onError: () => {
        setSseStatus("error");
      },
    });

    sseCleanupRef.current = cleanup;
    setSseStatus("connected");

    return () => {
      cleanup();
      sseCleanupRef.current = null;
    };
  }, [id, data, refetch]);

  const handleCancel = async () => {
    if (!id) return;
    if (
      !confirm(
        "Are you sure you want to cancel this investigation? This cannot be undone.",
      )
    ) {
      return;
    }
    try {
      await cancelMutation.mutateAsync({ investigationId: id });
      refetch();
    } catch (err) {
      console.error("Failed to cancel investigation:", err);
    }
  };

  if (!id) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">Investigation ID not provided</p>
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load investigation: {error?.message || "Not found"}
          </p>
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  const isComplete = [
    "completed",
    "failed",
    "cancelled",
    "inconclusive",
  ].includes(data.status);

  // Map investigation status to terminal step name
  const terminalStepMap: Record<string, string> = {
    completed: "complete",
    failed: "fail",
    cancelled: "cancelled",
    inconclusive: "complete",
  };
  const currentStep = isComplete
    ? terminalStepMap[data.status] || "complete"
    : data.main_branch.current_step;

  return (
    <InvestigationFeedbackProvider investigationId={id}>
      <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <Link to="/investigations">
              <Button variant="ghost" size="icon">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-2xl font-bold">Investigation</h1>
            <Badge variant={getStatusVariant(data.status)} className="text-sm">
              {data.status}
            </Badge>
            {sseStatus === "connected" && !isComplete && (
              <Badge variant="outline" className="text-xs gap-1">
                <span className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
                Live
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Codify Button - only for completed investigations */}
            {isMember && isComplete && data.main_branch.synthesis && (
              <CodifyWidget
                investigationId={id}
                confidence={
                  typeof (data.main_branch.synthesis as Record<string, unknown>)
                    ?.confidence === "number"
                    ? ((data.main_branch.synthesis as Record<string, unknown>)
                        .confidence as number)
                    : 0
                }
                isComplete={isComplete}
              />
            )}

            {/* Share Button */}
            <div className="relative">
              <Button
                variant="outline"
                className="gap-2"
                onClick={() => setShowShareMenu(!showShareMenu)}
              >
                <Share2 className="h-4 w-4" />
                Share
                <ChevronDown className="h-3 w-3" />
              </Button>
              <ShareMenu
                isOpen={showShareMenu}
                onClose={() => setShowShareMenu(false)}
              />
            </div>
          </div>
        </div>

        {/* Main Investigation Panel */}
        <div className="flex-1 overflow-auto">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Investigation Progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Step Timeline */}
              <div className="p-4 bg-muted/50 rounded-lg">
                <StepTimeline
                  currentStep={currentStep}
                  stepHistory={data.main_branch.step_history || []}
                  animated
                />

                {/* Cancel Button - only show when investigation is active */}
                {isMember && !isComplete && (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="mt-4 gap-2"
                    onClick={handleCancel}
                    disabled={cancelMutation.isPending}
                  >
                    {cancelMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <XCircle className="h-4 w-4" />
                    )}
                    Cancel Investigation
                  </Button>
                )}
              </div>

              {/* Matched Patterns */}
              {data.main_branch.matched_patterns &&
                data.main_branch.matched_patterns.length > 0 && (
                  <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                    <PatternList patterns={data.main_branch.matched_patterns} />
                  </div>
                )}

              {/* Synthesis */}
              {data.main_branch.synthesis && (
                <SynthesisCard
                  synthesis={data.main_branch.synthesis}
                  investigationId={id}
                />
              )}

              {/* Evidence - formatted nicely */}
              {data.main_branch.evidence.length > 0 && (
                <EvidenceList evidence={data.main_branch.evidence} />
              )}

              {/* Empty state */}
              {!data.main_branch.synthesis &&
                data.main_branch.evidence.length === 0 && (
                  <div className="flex items-center justify-center h-32 text-muted-foreground">
                    <div className="text-center">
                      <Bot className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">Investigation in progress...</p>
                    </div>
                  </div>
                )}
            </CardContent>
          </Card>
        </div>
      </div>
    </InvestigationFeedbackProvider>
  );
}
