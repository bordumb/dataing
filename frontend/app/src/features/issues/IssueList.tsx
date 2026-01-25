import { useState } from "react";
import { Link } from "react-router-dom";
import type { UseQueryResult } from "@tanstack/react-query";
import { Plus, Search, Filter, ChevronLeft, ChevronRight } from "lucide-react";
import {
  useIssues,
  getStatusVariant,
  getStatusLabel,
  getPriorityVariant,
  getSeverityVariant,
} from "@/lib/api/issues";
import type { IssueResponse, IssueListResponse } from "@/lib/api/issues";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AsyncBoundary } from "@/components/async-boundary";
import { formatDate } from "@/lib/utils";

interface IssueFilters {
  status?: string;
  priority?: string;
  severity?: string;
  search?: string;
  cursor?: string;
}

function IssueCard({ issue }: { issue: IssueResponse }) {
  return (
    <Link to={`/issues/${issue.id}`}>
      <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground font-mono text-sm">
                #{issue.number}
              </span>
              <CardTitle className="text-lg">{issue.title}</CardTitle>
            </div>
            <div className="flex items-center gap-2">
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
              <Badge variant={getStatusVariant(issue.status)}>
                {getStatusLabel(issue.status)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <div className="flex items-center gap-4">
              {issue.dataset_id && <span>Dataset: {issue.dataset_id}</span>}
              {issue.labels.length > 0 && (
                <div className="flex items-center gap-1">
                  {issue.labels.slice(0, 3).map((label) => (
                    <Badge key={label} variant="outline" className="text-xs">
                      {label}
                    </Badge>
                  ))}
                  {issue.labels.length > 3 && (
                    <span className="text-xs">+{issue.labels.length - 3}</span>
                  )}
                </div>
              )}
            </div>
            <span>Updated: {formatDate(issue.updated_at)}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function IssueListContent({
  data,
  onNextPage,
  onPrevPage,
  hasPrevPage,
}: {
  data: IssueListResponse;
  onNextPage: () => void;
  onPrevPage: () => void;
  hasPrevPage: boolean;
}) {
  if (data.items.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-muted-foreground">No issues found.</p>
          <Link to="/issues/new">
            <Button className="mt-4">Create your first issue</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {data.items.map((issue) => (
        <IssueCard key={issue.id} issue={issue} />
      ))}

      {(data.has_more || hasPrevPage) && (
        <div className="flex items-center justify-between pt-4">
          <Button
            variant="outline"
            disabled={!hasPrevPage}
            onClick={onPrevPage}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            {data.total} total issues
          </span>
          <Button
            variant="outline"
            disabled={!data.has_more}
            onClick={onNextPage}
          >
            Next
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  );
}

export function IssueList() {
  const [filters, setFilters] = useState<IssueFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [cursorHistory, setCursorHistory] = useState<string[]>([]);

  const query = useIssues({
    status: filters.status,
    priority: filters.priority,
    severity: filters.severity,
    search: filters.search,
    cursor: filters.cursor,
  });

  const handleSearch = () => {
    setFilters((prev) => ({
      ...prev,
      search: searchInput || undefined,
      cursor: undefined,
    }));
    setCursorHistory([]);
  };

  const handleFilterChange = (
    key: keyof IssueFilters,
    value: string | undefined,
  ) => {
    setFilters((prev) => ({ ...prev, [key]: value, cursor: undefined }));
    setCursorHistory([]);
  };

  const handleNextPage = () => {
    const nextCursor = query.data?.next_cursor;
    if (nextCursor) {
      setCursorHistory((prev) => [...prev, filters.cursor || ""]);
      setFilters((prev) => ({ ...prev, cursor: nextCursor }));
    }
  };

  const handlePrevPage = () => {
    if (cursorHistory.length > 0) {
      const prevCursor = cursorHistory[cursorHistory.length - 1];
      setCursorHistory((prev) => prev.slice(0, -1));
      setFilters((prev) => ({ ...prev, cursor: prevCursor || undefined }));
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Issues</h1>
        <Link to="/issues/new">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            New Issue
          </Button>
        </Link>
      </div>

      <div className="flex items-center gap-4 mb-6">
        <div className="flex items-center gap-2 flex-1">
          <Input
            placeholder="Search issues..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="max-w-sm"
          />
          <Button variant="outline" size="icon" onClick={handleSearch}>
            <Search className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />

          <Select
            value={filters.status || "all"}
            onValueChange={(v) =>
              handleFilterChange("status", v === "all" ? undefined : v)
            }
          >
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="triaged">Triaged</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="blocked">Blocked</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filters.priority || "all"}
            onValueChange={(v) =>
              handleFilterChange("priority", v === "all" ? undefined : v)
            }
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Priority</SelectItem>
              <SelectItem value="P0">P0</SelectItem>
              <SelectItem value="P1">P1</SelectItem>
              <SelectItem value="P2">P2</SelectItem>
              <SelectItem value="P3">P3</SelectItem>
              <SelectItem value="P4">P4</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filters.severity || "all"}
            onValueChange={(v) =>
              handleFilterChange("severity", v === "all" ? undefined : v)
            }
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="Severity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Severity</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <AsyncBoundary
        query={query as unknown as UseQueryResult<IssueListResponse, Error>}
      >
        {(data) => (
          <IssueListContent
            data={data}
            onNextPage={handleNextPage}
            onPrevPage={handlePrevPage}
            hasPrevPage={cursorHistory.length > 0}
          />
        )}
      </AsyncBoundary>
    </div>
  );
}
