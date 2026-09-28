import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  ArrowLeft,
  RefreshCw,
  Loader2,
  Play,
  X,
  Search,
  Lightbulb,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";
import {
  useIssue,
  useIssueInvestigationRuns,
  useSpawnInvestigation,
  useInvalidateIssues,
  getStatusVariant,
  getStatusLabel,
  getPriorityVariant,
  getSeverityVariant,
} from "@/lib/api/issues";
import { useRole } from "@/lib/auth";
import type {
  IssueResponse,
  InvestigationRunResponse,
  InvestigationRunListResponse,
} from "@/lib/api/issues";
import { errorText } from "@/lib/api/error-message";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AsyncBoundary } from "@/components/async-boundary";
import { Markdown } from "@/components/markdown";
import { formatDate } from "@/lib/utils";

import { IssueSidebar } from "./IssueSidebar";
import { IssueThread } from "./thread/IssueThread";

interface InvestigationSummaryCardProps {
  issueId: string;
}

function InvestigationSummaryCard({ issueId }: InvestigationSummaryCardProps) {
  const query = useIssueInvestigationRuns(issueId);

  // Get the latest completed investigation run
  const latestRun =
    query.data?.items?.find(
      (run: InvestigationRunResponse) =>
        run.synthesis_summary && run.completed_at,
    ) || query.data?.items?.[0];

  if (query.isLoading) {
    return null; // Don't show loading state, will show when data arrives
  }

  if (!latestRun?.synthesis_summary) {
    return null; // No summary available
  }

  return (
    <Card className="border-l-4 border-l-primary bg-primary/5">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-primary" />
            Investigation Summary
          </CardTitle>
          {latestRun.confidence && (
            <Badge variant="outline" className="text-xs">
              {Math.round(latestRun.confidence * 100)}% confidence
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {latestRun.root_cause_tag && (
          <Badge variant="secondary">{latestRun.root_cause_tag}</Badge>
        )}
        <p className="text-sm leading-relaxed">{latestRun.synthesis_summary}</p>
        <Link
          to={`/investigations/${latestRun.investigation_id}`}
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          View full investigation
          <ArrowRight className="h-3 w-3" />
        </Link>
      </CardContent>
    </Card>
  );
}

/** The symptom a run's brief states, for its one-line label. */
function briefSymptom(run: InvestigationRunResponse): string {
  const symptom = run.brief?.symptom;
  return typeof symptom === "string" ? symptom : "";
}

interface InvestigationRunsSectionProps {
  issueId: string;
  datasetId?: string | null;
}

function InvestigationRunsSection({
  issueId,
  datasetId,
}: InvestigationRunsSectionProps) {
  const [showModal, setShowModal] = useState(false);
  const [focusPrompt, setFocusPrompt] = useState("");
  const [executionProfile, setExecutionProfile] = useState("standard");
  const query = useIssueInvestigationRuns(issueId);
  const spawnInvestigation = useSpawnInvestigation();
  const { isMember } = useRole();
  const invalidate = useInvalidateIssues();

  const handleSpawn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!focusPrompt.trim()) return;

    try {
      await spawnInvestigation.mutateAsync({
        issueId,
        data: {
          brief: { version: 1, symptom: focusPrompt.trim() },
          execution_profile: executionProfile as "safe" | "standard" | "deep",
          dataset_id: datasetId || undefined,
        },
      });
      setShowModal(false);
      setFocusPrompt("");
      invalidate.invalidateInvestigationRuns(issueId);
    } catch (error) {
      toast.error("Couldn't start the investigation", {
        description: errorText(error),
      });
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="h-4 w-4" />
              Investigation Runs
            </CardTitle>
            {isMember && (
              <Button size="sm" onClick={() => setShowModal(true)}>
                <Play className="h-4 w-4 mr-1" />
                Run Investigation
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <AsyncBoundary
            query={
              query as unknown as UseQueryResult<
                InvestigationRunListResponse,
                Error
              >
            }
          >
            {(data) => (
              <div className="space-y-2">
                {data.items.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No investigations run yet.
                  </p>
                ) : (
                  data.items.map((run: InvestigationRunResponse) => (
                    <Link
                      key={run.id}
                      to={`/investigations/${run.investigation_id}`}
                      className="block p-3 bg-muted/50 rounded-lg hover:bg-muted transition-colors"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">
                          {briefSymptom(run).slice(0, 50)}
                          {briefSymptom(run).length > 50 ? "..." : ""}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {run.execution_profile}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{formatDate(run.created_at)}</span>
                        {run.confidence && (
                          <span>
                            • {Math.round(run.confidence * 100)}% confidence
                          </span>
                        )}
                        {run.root_cause_tag && (
                          <Badge variant="secondary" className="text-xs">
                            {run.root_cause_tag}
                          </Badge>
                        )}
                      </div>
                    </Link>
                  ))
                )}
              </div>
            )}
          </AsyncBoundary>
        </CardContent>
      </Card>

      {showModal && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setShowModal(false)}
          />
          <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-lg">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">Run Investigation</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowModal(false)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSpawn} className="space-y-4">
                  <div>
                    <Label>Focus Prompt</Label>
                    <Textarea
                      value={focusPrompt}
                      onChange={(e) => setFocusPrompt(e.target.value)}
                      placeholder="What should the investigation focus on?"
                      className="mt-1.5"
                      rows={3}
                    />
                  </div>
                  <div>
                    <Label>Execution Profile</Label>
                    <Select
                      value={executionProfile}
                      onValueChange={setExecutionProfile}
                    >
                      <SelectTrigger className="mt-1.5">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="safe">
                          Safe - Limited queries
                        </SelectItem>
                        <SelectItem value="standard">
                          Standard - Balanced
                        </SelectItem>
                        <SelectItem value="deep">
                          Deep - Comprehensive
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {datasetId && (
                    <p className="text-sm text-muted-foreground">
                      Dataset:{" "}
                      <code className="bg-muted px-1">{datasetId}</code>
                    </p>
                  )}
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setShowModal(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      disabled={
                        spawnInvestigation.isPending || !focusPrompt.trim()
                      }
                    >
                      {spawnInvestigation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Play className="h-4 w-4 mr-2" />
                      )}
                      Start Investigation
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

interface IssueWorkspaceContentProps {
  issue: IssueResponse;
}

function IssueWorkspaceContent({ issue }: IssueWorkspaceContentProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link to="/issues">
          <Button variant="ghost" size="icon" aria-label="Back to issues">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-muted-foreground">
              #{issue.number}
            </span>
            <h1 className="text-2xl font-bold">{issue.title}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={getStatusVariant(issue.status)}>
              {getStatusLabel(issue.status)}
            </Badge>
            {issue.priority && (
              <Badge variant={getPriorityVariant(issue.priority)}>
                {issue.priority}
              </Badge>
            )}
            {issue.severity && (
              <Badge variant={getSeverityVariant(issue.severity)}>
                {issue.severity}
              </Badge>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* Thread column */}
        <div className="min-w-0 space-y-6">
          <InvestigationSummaryCard issueId={issue.id} />

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Description</CardTitle>
            </CardHeader>
            <CardContent>
              {issue.description ? (
                <Markdown>{issue.description}</Markdown>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  No description provided.
                </p>
              )}
            </CardContent>
          </Card>

          <IssueThread issueId={issue.id} />
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <IssueSidebar issue={issue} />
          <InvestigationRunsSection
            issueId={issue.id}
            datasetId={issue.dataset_id}
          />
        </div>
      </div>
    </div>
  );
}

export function IssueWorkspace() {
  const { id } = useParams<{ id: string }>();
  const query = useIssue(id ?? "");

  if (!id) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">Issue ID not provided</p>
          <Link to="/issues">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (query.error || !query.data) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load issue:{" "}
            {query.error ? String(query.error) : "Not found"}
          </p>
          <Link to="/issues">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return <IssueWorkspaceContent issue={query.data} />;
}
