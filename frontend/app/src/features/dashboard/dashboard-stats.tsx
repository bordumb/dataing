import { CheckCircle2, Database, Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardStats } from "@/lib/api/dashboard";

const STAT_CARDS = [
  { key: "activeInvestigations", title: "Active Investigations", Icon: Search },
  { key: "completedToday", title: "Completed Today", Icon: CheckCircle2 },
  { key: "dataSources", title: "Data Sources", Icon: Database },
] as const;

interface DashboardStatsCardsProps {
  stats: DashboardStats | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function DashboardStatsCards({
  stats,
  isLoading,
  isError,
}: DashboardStatsCardsProps) {
  return (
    <div className="space-y-2">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {STAT_CARDS.map(({ key, title, Icon }) => (
          <Card key={key}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{title}</CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold" aria-label={title}>
                  {stats ? stats[key] : "—"}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      {isError && (
        <p role="alert" className="text-sm text-destructive">
          Couldn't load dashboard stats.
        </p>
      )}
    </div>
  );
}
