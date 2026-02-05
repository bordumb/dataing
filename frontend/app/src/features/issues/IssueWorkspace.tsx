import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useRegisterPageContext } from "@/lib/assistant/page-context";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  ArrowLeft,
  RefreshCw,
  Send,
  Loader2,
  Play,
  X,
  Eye,
  EyeOff,
  Clock,
  User,
  Tag,
  MessageSquare,
  Search,
  Lightbulb,
  ArrowRight,
} from "lucide-react";
import {
  useIssue,
  useUpdateIssue,
  useIssueComments,
  useCreateIssueComment,
  useIssueWatchers,
  useWatchIssue,
  useUnwatchIssue,
  useIssueInvestigationRuns,
  useSpawnInvestigation,
  useInvalidateIssues,
  getStatusVariant,
  getStatusLabel,
  getPriorityVariant,
  getSeverityVariant,
} from "@/lib/api/issues";
import type {
  IssueResponse,
  IssueCommentResponse,
  IssueCommentListResponse,
  InvestigationRunResponse,
  InvestigationRunListResponse,
  WatcherListResponse,
} from "@/lib/api/issues";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
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
import { formatDate } from "@/lib/utils";

interface CommentsSectionProps {
  issueId: string;
}

function CommentsSection({ issueId }: CommentsSectionProps) {
  const [newComment, setNewComment] = useState("");
  const query = useIssueComments(issueId);
  const createComment = useCreateIssueComment();
  const invalidate = useInvalidateIssues();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;

    try {
      await createComment.mutateAsync({
        issueId,
        data: { body: newComment.trim() },
      });
      setNewComment("");
      invalidate.invalidateComments(issueId);
    } catch (error) {
      console.error("Failed to add comment:", error);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          Comments
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <AsyncBoundary
          query={
            query as unknown as UseQueryResult<IssueCommentListResponse, Error>
          }
        >
          {(data) => (
            <div className="space-y-3">
              {data.items.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No comments yet.
                </p>
              ) : (
                data.items.map((comment: IssueCommentResponse) => (
                  <div
                    key={comment.id}
                    className="p-3 bg-muted/50 rounded-lg text-sm"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">User</span>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(comment.created_at)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap">{comment.body}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </AsyncBoundary>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Add a comment..."
            disabled={createComment.isPending}
            className="flex-1"
          />
          <Button
            type="submit"
            size="icon"
            disabled={createComment.isPending || !newComment.trim()}
          >
            {createComment.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

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
  const invalidate = useInvalidateIssues();

  const handleSpawn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!focusPrompt.trim()) return;

    try {
      await spawnInvestigation.mutateAsync({
        issueId,
        data: {
          focus_prompt: focusPrompt.trim(),
          execution_profile: executionProfile as "safe" | "standard" | "deep",
          dataset_id: datasetId || undefined,
        },
      });
      setShowModal(false);
      setFocusPrompt("");
      invalidate.invalidateInvestigationRuns(issueId);
    } catch (error) {
      console.error("Failed to spawn investigation:", error);
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
            <Button size="sm" onClick={() => setShowModal(true)}>
              <Play className="h-4 w-4 mr-1" />
              Run Investigation
            </Button>
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
                          {run.focus_prompt?.slice(0, 50)}
                          {(run.focus_prompt?.length ?? 0) > 50 ? "..." : ""}
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

interface WatchersSectionProps {
  issueId: string;
}

function WatchersSection({ issueId }: WatchersSectionProps) {
  const query = useIssueWatchers(issueId);
  const watchIssue = useWatchIssue();
  const unwatchIssue = useUnwatchIssue();
  const invalidate = useInvalidateIssues();
  const [isWatching, setIsWatching] = useState(false);

  const handleToggleWatch = async () => {
    try {
      if (isWatching) {
        await unwatchIssue.mutateAsync({ issueId });
      } else {
        await watchIssue.mutateAsync({ issueId });
      }
      setIsWatching(!isWatching);
      invalidate.invalidateWatchers(issueId);
    } catch (error) {
      console.error("Failed to toggle watch:", error);
    }
  };

  const isPending = watchIssue.isPending || unwatchIssue.isPending;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium flex items-center gap-2">
          <Eye className="h-4 w-4" />
          Watchers
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={handleToggleWatch}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : isWatching ? (
            <>
              <EyeOff className="h-4 w-4 mr-1" />
              Unwatch
            </>
          ) : (
            <>
              <Eye className="h-4 w-4 mr-1" />
              Watch
            </>
          )}
        </Button>
      </div>
      <AsyncBoundary
        query={query as unknown as UseQueryResult<WatcherListResponse, Error>}
      >
        {(data) => (
          <p className="text-sm text-muted-foreground">
            {data.total} {data.total === 1 ? "watcher" : "watchers"}
          </p>
        )}
      </AsyncBoundary>
    </div>
  );
}

interface IssueWorkspaceContentProps {
  issue: IssueResponse;
}

function IssueWorkspaceContent({ issue }: IssueWorkspaceContentProps) {
  const updateIssue = useUpdateIssue();
  const invalidate = useInvalidateIssues();
  const [isEditingStatus, setIsEditingStatus] = useState(false);

  const pageCtx = useMemo(
    () => ({
      pageType: "issue_detail",
      pageTitle: `Issue #${issue.number}: ${issue.title}`,
      pageData: {
        issueId: issue.id,
        title: issue.title,
        status: issue.status,
        priority: issue.priority ?? null,
        severity: issue.severity ?? null,
        labels: issue.labels,
      },
    }),
    [issue],
  );
  useRegisterPageContext(pageCtx);

  const handleStatusChange = async (newStatus: string) => {
    try {
      await updateIssue.mutateAsync({
        issueId: issue.id,
        data: { status: newStatus },
      });
      invalidate.invalidateDetail(issue.id);
      invalidate.invalidateList();
      setIsEditingStatus(false);
    } catch (error) {
      console.error("Failed to update status:", error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Link to="/issues">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-muted-foreground font-mono">
                #{issue.number}
              </span>
              <h1 className="text-2xl font-bold">{issue.title}</h1>
            </div>
            <div className="flex items-center gap-2">
              {isEditingStatus ? (
                <Select
                  value={issue.status}
                  onValueChange={handleStatusChange}
                  disabled={updateIssue.isPending}
                >
                  <SelectTrigger className="w-[140px] h-7">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="triaged">Triaged</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="blocked">Blocked</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <Badge
                  variant={getStatusVariant(issue.status)}
                  className="cursor-pointer"
                  onClick={() => setIsEditingStatus(true)}
                >
                  {getStatusLabel(issue.status)}
                </Badge>
              )}
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
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Investigation Summary - prominent placement */}
          <InvestigationSummaryCard issueId={issue.id} />

          {/* Description */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Description</CardTitle>
            </CardHeader>
            <CardContent>
              {issue.description ? (
                <p className="text-sm whitespace-pre-wrap">
                  {issue.description}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground italic">
                  No description provided.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Investigation Runs */}
          <InvestigationRunsSection
            issueId={issue.id}
            datasetId={issue.dataset_id}
          />

          {/* Comments */}
          <CommentsSection issueId={issue.id} />
        </div>

        {/* Right rail */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Dataset */}
              {issue.dataset_id && (
                <div>
                  <span className="text-sm font-medium flex items-center gap-2 mb-1">
                    <Tag className="h-4 w-4" />
                    Dataset
                  </span>
                  <code className="text-sm bg-muted px-2 py-1 rounded">
                    {issue.dataset_id}
                  </code>
                </div>
              )}

              {/* Assignee */}
              <div>
                <span className="text-sm font-medium flex items-center gap-2 mb-1">
                  <User className="h-4 w-4" />
                  Assignee
                </span>
                <p className="text-sm text-muted-foreground">
                  {issue.assignee_user_id || "Unassigned"}
                </p>
              </div>

              {/* Labels */}
              {issue.labels.length > 0 && (
                <div>
                  <span className="text-sm font-medium flex items-center gap-2 mb-2">
                    <Tag className="h-4 w-4" />
                    Labels
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {issue.labels.map((label) => (
                      <Badge key={label} variant="outline" className="text-xs">
                        {label}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Watchers */}
              <WatchersSection issueId={issue.id} />

              {/* Timestamps */}
              <div>
                <span className="text-sm font-medium flex items-center gap-2 mb-1">
                  <Clock className="h-4 w-4" />
                  Timeline
                </span>
                <div className="text-sm text-muted-foreground space-y-1">
                  <p>Created: {formatDate(issue.created_at)}</p>
                  <p>Updated: {formatDate(issue.updated_at)}</p>
                  {issue.closed_at && (
                    <p>Closed: {formatDate(issue.closed_at)}</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
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
