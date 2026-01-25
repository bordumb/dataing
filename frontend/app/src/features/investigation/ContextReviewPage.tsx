import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { EmptyState } from "@/components/shared/empty-state";
import {
  useGetApprovalRequestApiV1ApprovalsApprovalIdGet,
  useApproveRequestApiV1ApprovalsApprovalIdApprovePost,
  useRejectRequestApiV1ApprovalsApprovalIdRejectPost,
  getListPendingApprovalsApiV1ApprovalsPendingGetQueryKey,
} from "@/lib/api/generated/approvals/approvals";
import { ContextReview } from "./context-review";

export function ContextReviewPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    data: approval,
    isLoading,
    error,
  } = useGetApprovalRequestApiV1ApprovalsApprovalIdGet(approvalId || "", {
    query: { enabled: !!approvalId },
  });

  const approveMutation = useApproveRequestApiV1ApprovalsApprovalIdApprovePost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListPendingApprovalsApiV1ApprovalsPendingGetQueryKey(),
        });
        toast.success("Investigation approved and resumed");
        navigate(`/investigations/${approval?.investigation_id}`);
      },
      onError: (err: Error) => {
        toast.error(`Failed to approve: ${err.message}`);
      },
    },
  });

  const rejectMutation = useRejectRequestApiV1ApprovalsApprovalIdRejectPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListPendingApprovalsApiV1ApprovalsPendingGetQueryKey(),
        });
        toast.success("Investigation rejected");
        navigate("/investigations");
      },
      onError: (err: Error) => {
        toast.error(`Failed to reject: ${err.message}`);
      },
    },
  });

  const handleApprove = async (comment?: string) => {
    if (!approvalId) return;
    await approveMutation.mutateAsync({
      approvalId,
      data: { comment: comment || null },
    });
  };

  const handleReject = async (reason: string) => {
    if (!approvalId) return;
    await rejectMutation.mutateAsync({
      approvalId,
      data: { reason },
    });
  };

  if (!approvalId) {
    return (
      <Card>
        <CardContent className="py-12">
          <EmptyState
            icon={Loader2}
            title="Approval ID not provided"
            description="Please access this page from an approval notification link."
          />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !approval) {
    return (
      <Card>
        <CardContent className="py-12">
          <EmptyState
            icon={Loader2}
            title="Approval request not found"
            description="This approval request may have been completed or does not exist."
            action={
              <Link to="/investigations">
                <Button>Back to Investigations</Button>
              </Link>
            }
          />
        </CardContent>
      </Card>
    );
  }

  // Check if already decided
  if (approval.decision) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Link to="/investigations">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-2xl font-bold">Context Review</h1>
        </div>
        <Card>
          <CardContent className="py-12">
            <EmptyState
              icon={Loader2}
              title={`This request has been ${approval.decision}`}
              description={
                approval.comment || "No additional details provided."
              }
              action={
                <Link to={`/investigations/${approval.investigation_id}`}>
                  <Button>View Investigation</Button>
                </Link>
              }
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  // Build context object for ContextReview component
  const context = {
    query: (approval.context?.query as string) || "Query not available",
    purpose:
      (approval.context?.purpose as string) ||
      `Review context for investigation ${approval.investigation_id}`,
    tables_accessed: (approval.context?.tables_accessed as string[]) || [],
    estimated_rows: (approval.context?.estimated_rows as number) || 0,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/investigations">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Context Review</h1>
      </div>

      <ContextReview
        investigationId={approval.investigation_id}
        context={context}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}
