import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
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
        action={
          isMember ? (
            <Button asChild>
              <Link to="/investigations/new">
                <Plus className="mr-2 h-4 w-4" />
                New Investigation
              </Link>
            </Button>
          ) : undefined
        }
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
