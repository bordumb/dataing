/**
 * The issue page, laid out like 0001_issue_chat_mockup.html (spec 0001 §8.1):
 * a one-row top bar, then the shared thread (1fr) beside one sidebar panel
 * (300px), stacked on narrow screens.
 */

import { useParams, Link } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";

import { useIssue, getStatusLabel } from "@/lib/api/issues";
import type { IssueResponse } from "@/lib/api/issues";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

import { IssueSidebar } from "./IssueSidebar";
import { IssueHubProvider } from "./hub/IssueHub";
import { IssueThread } from "./thread/IssueThread";
import { Pill, issueStatusTone } from "./thread/Pill";

/** "#42 · title · In progress · P1 ········· dataset analytics.public.orders" */
function IssueTopBar({ issue }: { issue: IssueResponse }) {
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border bg-card px-5 py-3">
      <Link
        to="/issues"
        aria-label="Back to issues"
        className="-ml-1.5 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
      </Link>
      <Pill>#{issue.number}</Pill>
      <h1 className="min-w-0 text-base font-semibold">{issue.title}</h1>
      <Pill tone={issueStatusTone(issue.status)}>
        {getStatusLabel(issue.status)}
      </Pill>
      {issue.priority && <Pill>{issue.priority}</Pill>}
      {issue.dataset_id && (
        <span className="ml-auto text-sm text-muted-foreground">
          dataset{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
            {issue.dataset_id}
          </code>
        </span>
      )}
    </header>
  );
}

function IssueWorkspaceContent({ issue }: { issue: IssueResponse }) {
  return (
    <IssueHubProvider
      issueId={issue.id}
      issueTitle={issue.title}
      datasetId={issue.dataset_id ?? null}
    >
      {/* The top bar runs edge to edge under the app header. */}
      <div className="-mx-6 -mt-6">
        <IssueTopBar issue={issue} />
      </div>
      <div className="mx-auto mt-4 grid max-w-[1200px] gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <IssueThread issueId={issue.id} />
        <IssueSidebar issue={issue} />
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
