/**
 * Branch tree visualization component.
 * Shows the relationship between main and user branches.
 */

import { GitBranch, GitMerge, User } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { BranchState } from "@/lib/api/investigations";

interface BranchNodeProps {
  branch: BranchState;
  label: string;
  isMain?: boolean;
  ownerName?: string;
  isSelected?: boolean;
  onClick?: () => void;
}

function BranchNode({
  branch,
  label,
  isMain,
  ownerName,
  isSelected,
  onClick,
}: BranchNodeProps) {
  const statusColor =
    {
      active: "bg-blue-500",
      completed: "bg-green-500",
      suspended: "bg-yellow-500",
      merged: "bg-purple-500",
      abandoned: "bg-red-500",
    }[branch.status] || "bg-gray-500";

  return (
    <button
      onClick={onClick}
      className={`
        flex items-center gap-2 px-3 py-2 rounded-lg border transition-all
        ${
          isSelected
            ? "border-primary bg-primary/5 ring-2 ring-primary/20"
            : "border-border hover:border-primary/50 hover:bg-muted/50"
        }
        ${onClick ? "cursor-pointer" : "cursor-default"}
      `}
    >
      <div className={`h-2 w-2 rounded-full ${statusColor}`} />
      <GitBranch
        className={`h-4 w-4 ${isMain ? "text-primary" : "text-muted-foreground"}`}
      />
      <span className="text-sm font-medium">{label}</span>
      {ownerName && (
        <Badge variant="outline" className="gap-1 text-xs">
          <User className="h-3 w-3" />
          {ownerName}
        </Badge>
      )}
      {branch.can_merge && (
        <Badge
          variant="secondary"
          className="gap-1 text-xs bg-purple-100 text-purple-700"
        >
          <GitMerge className="h-3 w-3" />
          Ready to merge
        </Badge>
      )}
    </button>
  );
}

interface BranchTreeProps {
  mainBranch: BranchState;
  userBranch: BranchState | null;
  currentUserName?: string;
  selectedBranchId?: string;
  onSelectBranch?: (branchId: string) => void;
}

export function BranchTree({
  mainBranch,
  userBranch,
  currentUserName,
  selectedBranchId,
  onSelectBranch,
}: BranchTreeProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <GitBranch className="h-4 w-4" />
        <span>Branch Tree</span>
      </div>

      <div className="relative pl-4">
        {/* Main branch */}
        <div className="relative">
          <BranchNode
            branch={mainBranch}
            label="Main Branch"
            isMain
            isSelected={selectedBranchId === mainBranch.branch_id}
            onClick={
              onSelectBranch
                ? () => onSelectBranch(mainBranch.branch_id)
                : undefined
            }
          />

          {/* Connection line to user branch */}
          {userBranch && (
            <div className="absolute left-6 top-full h-6 w-0.5 bg-border" />
          )}
        </div>

        {/* User branch (forked from main) */}
        {userBranch && (
          <div className="relative mt-2 ml-8">
            {/* Fork indicator */}
            <div className="absolute -left-8 top-1/2 h-0.5 w-6 bg-border" />
            <div className="absolute -left-8 -top-4 h-6 w-0.5 bg-border" />

            <BranchNode
              branch={userBranch}
              label="Your Branch"
              ownerName={currentUserName}
              isSelected={selectedBranchId === userBranch.branch_id}
              onClick={
                onSelectBranch
                  ? () => onSelectBranch(userBranch.branch_id)
                  : undefined
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
