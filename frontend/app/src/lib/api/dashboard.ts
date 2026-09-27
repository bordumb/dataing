import { getStatsApiV1DashboardStatsGet } from "./generated/dashboard/dashboard";

export interface DashboardStats {
  activeInvestigations: number;
  completedToday: number;
  dataSources: number;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const stats = await getStatsApiV1DashboardStatsGet();
  return {
    activeInvestigations: stats.active_investigations,
    completedToday: stats.completed_today,
    dataSources: stats.data_sources,
  };
}
