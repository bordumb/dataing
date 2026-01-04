import type { AuditEvent, UsagePoint } from "@/types/admin";
import { getInvestigations } from "./investigations";
import { getOrgStats } from "./analytics";

export async function getAuditLog(): Promise<AuditEvent[]> {
  try {
    // Generate audit events from recent investigations
    const result = await getInvestigations();
    const recentInvestigations = result.investigations
      .filter((inv) => inv.status === "resolved")
      .slice(0, 10);

    return recentInvestigations.map((inv) => ({
      id: `audit-${inv.id}`,
      timestamp: inv.updated_at,
      actor: {
        id: inv.triggered_by.id,
        email: inv.triggered_by.email,
        type: "user" as const,
      },
      action: "investigation.completed",
      resource: {
        type: "investigation",
        id: inv.id,
      },
    }));
  } catch (error) {
    console.error("Error fetching audit log:", error);
    return [];
  }
}

export async function getOrgUsage(): Promise<{ investigations_mtd: number; api_calls_mtd: number }> {
  try {
    const stats = await getOrgStats();

    // Calculate total investigations from activity heatmap
    const totalInvestigations = stats.activity_heatmap.reduce(
      (sum, item) => sum + item.count,
      0
    );

    return {
      investigations_mtd: totalInvestigations,
      api_calls_mtd: totalInvestigations * 4000, // Estimate ~4000 API calls per investigation
    };
  } catch (error) {
    console.error("Error fetching org usage:", error);
    return {
      investigations_mtd: 0,
      api_calls_mtd: 0,
    };
  }
}

export async function getUsageSeries(): Promise<UsagePoint[]> {
  try {
    const stats = await getOrgStats();

    // Group heatmap data by week
    const weeklyData: { [week: string]: number } = {};

    stats.activity_heatmap.forEach((item) => {
      const date = new Date(item.date);
      const weekNumber = Math.floor(date.getDate() / 7) + 1;
      const weekKey = `Week ${weekNumber}`;

      weeklyData[weekKey] = (weeklyData[weekKey] || 0) + item.count;
    });

    // Convert to array and take last 4 weeks
    const series = Object.entries(weeklyData)
      .map(([label, value]) => ({ label, value }))
      .slice(-4);

    return series.length > 0 ? series : [
      { label: "Week 1", value: 0 },
      { label: "Week 2", value: 0 },
      { label: "Week 3", value: 0 },
      { label: "Week 4", value: 0 },
    ];
  } catch (error) {
    console.error("Error fetching usage series:", error);
    return [];
  }
}
