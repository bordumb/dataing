/**
 * Merge point indicator component.
 * Shows when branches can be merged and provides merge action.
 */

import { GitMerge, ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import type { BranchState } from "@/lib/api/investigations";

interface MergeIndicatorProps {
  sourceBranch: BranchState;
  targetBranch: BranchState;
  onMerge?: () => void;
  isPending?: boolean;
}

export function MergeIndicator({
  sourceBranch,
  targetBranch: _targetBranch,
  onMerge,
  isPending,
}: MergeIndicatorProps) {
  if (!sourceBranch.can_merge) {
    return null;
  }

  return (
    <Card className="border-purple-200 bg-purple-50/50 dark:border-purple-800 dark:bg-purple-900/20">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900">
              <GitMerge className="h-5 w-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm font-medium">Ready to Merge</p>
              <p className="text-xs text-muted-foreground">
                Your branch findings can be merged into the main investigation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className="font-medium">Your Branch</span>
              <ArrowRight className="h-3 w-3" />
              <span className="font-medium">Main</span>
            </div>

            {onMerge && (
              <Button
                size="sm"
                variant="outline"
                onClick={onMerge}
                disabled={isPending}
                className="gap-1 border-purple-300 text-purple-700 hover:bg-purple-100"
              >
                <GitMerge className="h-4 w-4" />
                Merge
              </Button>
            )}
          </div>
        </div>

        {/* Merge preview */}
        {sourceBranch.synthesis && (
          <div className="mt-3 rounded-md bg-white/50 dark:bg-black/20 p-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">
              Synthesis to merge:
            </p>
            <p className="text-sm">
              {(() => {
                if (typeof sourceBranch.synthesis !== "object") {
                  return String(sourceBranch.synthesis).slice(0, 200);
                }
                const syn = sourceBranch.synthesis as Record<string, unknown>;
                if (typeof syn.summary === "string")
                  return syn.summary.slice(0, 200);
                if (typeof syn.root_cause === "string")
                  return syn.root_cause.slice(0, 200);
                return JSON.stringify(sourceBranch.synthesis).slice(0, 200);
              })()}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface MergeStatusProps {
  merged: boolean;
  mergedAt?: string;
}

export function MergeStatus({ merged, mergedAt }: MergeStatusProps) {
  if (!merged) return null;

  return (
    <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
      <Check className="h-4 w-4" />
      <span>
        Merged{mergedAt ? ` on ${new Date(mergedAt).toLocaleDateString()}` : ""}
      </span>
    </div>
  );
}
