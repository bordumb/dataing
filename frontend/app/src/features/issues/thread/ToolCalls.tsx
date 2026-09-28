/**
 * The tools an agent reply used, collapsed to one line ("Ran 2 queries ▸").
 *
 * Expanded, each query shows the SQL with a copy button and the snapshot of
 * rows the agent saw, fetched from the query-results endpoint on demand.
 */

import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import {
  useQueryResult,
  type QueryResult,
  type ToolCall,
} from "@/lib/api/issue-threads";
import { cn } from "@/lib/utils";

const QUERY_TOOL = "run_query";

function plural(n: number, word: string, pluralWord = `${word}s`): string {
  return `${n} ${n === 1 ? word : pluralWord}`;
}

export function toolCallsSummary(calls: ToolCall[]): string {
  const queries = calls.filter((c) => c.tool === QUERY_TOOL).length;
  const others = calls.length - queries;
  const parts: string[] = [];
  if (queries > 0) parts.push(`Ran ${plural(queries, "query", "queries")}`);
  if (others > 0) {
    parts.push(
      queries > 0
        ? plural(others, "other tool call")
        : `Used ${plural(others, "tool")}`,
    );
  }
  return parts.join(" · ");
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard");
    }
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-6 gap-1 px-2 text-xs"
      onClick={copy}
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : "Copy SQL"}
    </Button>
  );
}

function ResultTable({ result }: { result: QueryResult }) {
  if (result.columns.length === 0) return null;
  return (
    <div className="max-h-72 overflow-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {result.columns.map((col) => (
              <th
                key={col.name}
                className="sticky top-0 border-b border-border bg-background px-2 py-1 text-left font-semibold text-muted-foreground"
              >
                {col.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i}>
              {result.columns.map((col) => (
                <td
                  key={col.name}
                  className="whitespace-nowrap border-b border-border px-2 py-1 font-mono"
                >
                  {formatCell(row[col.name])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QueryCall({
  call,
  issueId,
  threadId,
}: {
  call: ToolCall;
  issueId: string;
  threadId: string;
}) {
  const query = useQueryResult(issueId, threadId, call.query_result_id);
  const inputSql = typeof call.input.sql === "string" ? call.input.sql : "";
  const purpose =
    typeof call.input.purpose === "string" ? call.input.purpose : "";

  if (!call.query_result_id) {
    return (
      <div className="space-y-1 px-3 py-2">
        {inputSql && (
          <pre className="whitespace-pre-wrap font-mono text-xs">
            {inputSql}
          </pre>
        )}
        <p className="text-xs text-destructive">
          {call.summary || "The query didn't run."}
          {call.error_code ? ` (${call.error_code})` : ""}
        </p>
      </div>
    );
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading the query snapshot…
      </div>
    );
  }

  if (query.error || !query.data) {
    return (
      <p className="px-3 py-2 text-xs text-destructive">
        Couldn't load this query:{" "}
        {query.error instanceof Error ? query.error.message : "not found"}
      </p>
    );
  }

  const result = query.data;
  return (
    <div>
      {purpose && (
        <p className="px-3 pt-2 text-xs text-muted-foreground">{purpose}</p>
      )}
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <pre className="min-w-0 flex-1 whitespace-pre-wrap font-mono text-xs">
          {result.sql}
        </pre>
        <CopyButton text={result.sql} />
      </div>
      {result.error ? (
        <p className="px-3 py-2 text-xs text-destructive">{result.error}</p>
      ) : (
        <ResultTable result={result} />
      )}
      <p className="px-3 py-1.5 text-xs text-muted-foreground">
        {plural(result.row_count, "row")}
        {result.truncated
          ? ` · showing the first ${plural(result.rows.length, "row")}`
          : ""}{" "}
        · {result.duration_ms} ms · {result.dialect}
      </p>
    </div>
  );
}

function OtherCall({ call }: { call: ToolCall }) {
  return (
    <div className="px-3 py-2 text-xs">
      <span className="font-mono font-medium">{call.tool}</span>
      <span
        className={cn(
          "ml-2",
          call.status === "error"
            ? "text-destructive"
            : "text-muted-foreground",
        )}
      >
        {call.summary}
        {call.error_code ? ` (${call.error_code})` : ""}
      </span>
    </div>
  );
}

interface ToolCallsProps {
  calls: ToolCall[];
  issueId: string;
  threadId: string;
}

export function ToolCalls({ calls, issueId, threadId }: ToolCallsProps) {
  const [open, setOpen] = useState(false);
  if (calls.length === 0) return null;
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <div className="mt-2 overflow-hidden rounded-md border border-border">
      <button
        type="button"
        className="flex w-full items-center gap-1 bg-muted px-3 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Chevron className="h-3 w-3" />
        {toolCallsSummary(calls)}
      </button>
      {open && (
        <div className="divide-y divide-border">
          {calls.map((call) =>
            call.tool === QUERY_TOOL ? (
              <QueryCall
                key={call.id}
                call={call}
                issueId={issueId}
                threadId={threadId}
              />
            ) : (
              <OtherCall key={call.id} call={call} />
            ),
          )}
        </div>
      )}
    </div>
  );
}
