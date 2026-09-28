import { useParams, Link } from "react-router-dom";
import type { UseQueryResult } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, Loader2, Search } from "lucide-react";
import {
  useIssue,
  useIssueInvestigationRuns,
  getStatusVariant,
  getStatusLabel,
  getPriorityVariant,
  getSeverityVariant,
} from "@/lib/api/issues";
import type {
  IssueResponse,
  InvestigationRunResponse,
  InvestigationRunListResponse,
} from "@/lib/api/issues";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { AsyncBoundary } from "@/components/async-boundary";
import { Markdown } from "@/components/markdown";
import { formatDate } from "@/lib/utils";

import { IssueSidebar } from "./IssueSidebar";
import { IssueHubProvider } from "./hub/IssueHub";
import { useIssueHub } from "./hub/hub-context";
import { IssueThread } from "./thread/IssueThread";
import { ScratchChatsSection } from "./scratch/ScratchChatsSection";
import { Pill } from "./thread/Pill";

/** The symptom a run's brief states, for its one-line label. */
function briefSymptom(run: InvestigationRunResponse): string {
  const symptom = run.brief?.symptom;
  return typeof symptom === "string" ? symptom : "";
}

function RunState({ run }: { run: InvestigationRunResponse }) {
  if (run.outcome_verdict === "confirmed") {
    return <Pill tone="ok">confirmed</Pill>;
  }
  if (run.outcome_verdict === "rejected") {
    return <Pill tone="bad">rejected</Pill>;
  }
  if (run.completed_at) {
    return (
      <Pill tone="ok">
        done
        {typeof run.confidence === "number"
          ? ` · ${run.confidence.toFixed(2)}`
          : ""}
      </Pill>
    );
  }
  return <Pill tone="agent">running</Pill>;
}

function InvestigationRunsSection({ issueId }: { issueId: string }) {
  const query = useIssueInvestigationRuns(issueId);
  const hub = useIssueHub();

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Search className="h-4 w-4" />
            Investigations
          </CardTitle>
          {hub?.canWrite && hub.sharedThreadId && (
            <Button
              size="sm"
              variant="outline"
              disabled={hub.isRequestingDraft}
              onClick={() => void hub.investigateFrom(hub.sharedThreadId!)}
            >
              {hub.isRequestingDraft && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              Investigate…
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
                  No investigations yet. Investigate… hands the thread to one.
                </p>
              ) : (
                data.items.map((run: InvestigationRunResponse) => (
                  <Link
                    key={run.id}
                    to={`/investigations/${run.investigation_id}`}
                    className="block rounded-lg bg-muted/50 p-3 transition-colors hover:bg-muted"
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">
                        {briefSymptom(run) || "Investigation"}
                      </span>
                      <RunState run={run} />
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{formatDate(run.created_at)}</span>
                      <span>· {run.execution_profile}</span>
                      {run.parent_run_id && <span>· follow-up</span>}
                    </div>
                  </Link>
                ))
              )}
            </div>
          )}
        </AsyncBoundary>
      </CardContent>
    </Card>
  );
}

interface IssueWorkspaceContentProps {
  issue: IssueResponse;
}

function IssueWorkspaceContent({ issue }: IssueWorkspaceContentProps) {
  return (
    <IssueHubProvider
      issueId={issue.id}
      issueTitle={issue.title}
      datasetId={issue.dataset_id ?? null}
    >
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
            <InvestigationRunsSection issueId={issue.id} />
            <ScratchChatsSection issueId={issue.id} />
          </div>
        </div>
      </div>
    </IssueHubProvider>
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
