import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { InvestigateButton } from "@/features/issues/brief/StartInvestigation";
import { fetchDashboardStats } from "@/lib/api/dashboard";
import { DashboardStatsCards } from "./dashboard-stats";
import { RecentInvestigations } from "./recent-investigations";
import { PageHeader } from "@/components/shared/page-header";
import { useRole } from "@/lib/auth";

export function DashboardPage() {
  const {
    data: stats,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: fetchDashboardStats,
  });
  const { isMember } = useRole();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        action={isMember ? <InvestigateButton /> : undefined}
      />

      <DashboardStatsCards
        stats={stats}
        isLoading={isLoading}
        isError={isError}
      />

      {/* Recent Investigations */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Investigations</CardTitle>
        </CardHeader>
        <CardContent>
          <RecentInvestigations />
        </CardContent>
      </Card>
    </div>
  );
}
