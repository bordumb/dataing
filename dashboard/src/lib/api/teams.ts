import { api } from "./client";
import type { Dataset } from "@/types/dataset";
import type { Investigation } from "@/types/investigation";
import type { Team, TeamMember, TeamStats } from "@/types/team";

// Types for API responses
interface APITeam {
  id: string;
  name: string;
  description: string | null;
  organization_id: string;
  created_at: string;
  updated_at: string | null;
  stats?: {
    active_investigations: number;
    completed_investigations: number;
    avg_resolution_hours: number | null;
    dataset_count: number;
    member_count: number;
  };
}

interface APITeamMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  joined_at: string;
}

interface TeamsListResponse {
  teams: APITeam[];
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface TeamMembersResponse {
  members: APITeamMember[];
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface TeamDatasetsResponse {
  datasets: Array<{
    dataset_id: string;
    dataset_name: string;
    ownership_type: string;
    assigned_at: string;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

function mapAPITeam(apiTeam: APITeam): Team {
  return {
    id: apiTeam.id,
    name: apiTeam.name,
    description: apiTeam.description || "",
    slack_channel: `#${apiTeam.name.toLowerCase().replace(/\s+/g, "-")}`,
    on_call: "On-call rotation",
    dataset_count: apiTeam.stats?.dataset_count || 0,
    member_count: apiTeam.stats?.member_count || 0,
  };
}

export async function getTeams(): Promise<Team[]> {
  try {
    const data = await api.get<TeamsListResponse>("/api/v1/teams");
    return data.teams.map(mapAPITeam);
  } catch (error) {
    console.error("Error fetching teams:", error);
    // Fallback to demo data if API not available
    return getDemoTeams();
  }
}

export async function getTeam(teamId: string): Promise<Team> {
  try {
    const data = await api.get<{ team: APITeam; stats: TeamStats }>(`/api/v1/teams/${teamId}`);
    return {
      ...mapAPITeam(data.team),
      dataset_count: data.stats?.active_investigations || 0,
      member_count: data.team.stats?.member_count || 0,
    };
  } catch (error) {
    console.error("Error fetching team:", error);
    const teams = await getDemoTeams();
    const team = teams.find((t) => t.id === teamId);
    if (!team) throw new Error("Team not found");
    return team;
  }
}

export async function getTeamStats(teamId: string): Promise<TeamStats> {
  try {
    const data = await api.get<{ team: APITeam; stats: TeamStats }>(`/api/v1/teams/${teamId}`);
    return {
      active_investigations: data.stats?.active_investigations || 0,
      anomalies_30d: data.stats?.anomalies_30d || 0,
      mttr_hours: data.stats?.mttr_hours || 0,
      sla_pct: data.stats?.sla_pct || 0,
    };
  } catch (error) {
    console.error("Error fetching team stats:", error);
    return {
      active_investigations: 0,
      anomalies_30d: 0,
      mttr_hours: 0,
      sla_pct: 0,
    };
  }
}

export async function getTeamMembers(teamId: string): Promise<TeamMember[]> {
  try {
    const data = await api.get<TeamMembersResponse>(`/api/v1/teams/${teamId}/members`);
    return data.members.map((member) => ({
      id: member.user_id,
      name: member.name,
      email: member.email,
      avatar_url: `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(member.name)}`,
      role: member.role as "admin" | "member" | "viewer",
    }));
  } catch (error) {
    console.error("Error fetching team members:", error);
    return [];
  }
}

export async function getTeamDatasets(teamId: string): Promise<Dataset[]> {
  try {
    const data = await api.get<TeamDatasetsResponse>(`/api/v1/teams/${teamId}/datasets`);
    return data.datasets.map((ds) => ({
      id: ds.dataset_id,
      name: ds.dataset_name,
      description: `Owned by team - ${ds.ownership_type}`,
      owner_team_id: teamId,
      table_count: 1,
      investigation_count: 0,
      anomaly_count_30d: 0,
      freshness_status: "healthy" as const,
    }));
  } catch (error) {
    console.error("Error fetching team datasets:", error);
    return [];
  }
}

export async function getTeamInvestigations(
  teamId: string,
  { limit }: { limit?: number } = {}
): Promise<Investigation[]> {
  try {
    const params = new URLSearchParams({
      team_id: teamId,
      ...(limit && { limit: limit.toString() }),
    });
    const data = await api.get<{ investigations: Investigation[] }>(
      `/api/v1/investigations?${params}`
    );
    return data.investigations;
  } catch (error) {
    console.error("Error fetching team investigations:", error);
    return [];
  }
}

export async function createTeam(data: {
  name: string;
  description?: string;
}): Promise<Team> {
  const response = await api.post<{ team: APITeam }>("/api/v1/teams", data);
  return mapAPITeam(response.team);
}

export async function updateTeam(
  teamId: string,
  data: { name?: string; description?: string }
): Promise<Team> {
  const response = await api.put<{ team: APITeam }>(`/api/v1/teams/${teamId}`, data);
  return mapAPITeam(response.team);
}

export async function addTeamMember(
  teamId: string,
  data: { user_id: string; role?: string }
): Promise<void> {
  await api.post(`/api/v1/teams/${teamId}/members`, data);
}

export async function removeTeamMember(teamId: string, userId: string): Promise<void> {
  await api.delete(`/api/v1/teams/${teamId}/members/${userId}`);
}

// Fallback demo data
function getDemoTeams(): Team[] {
  return [
    {
      id: "team-001",
      name: "Revenue Ops",
      description: "Owns revenue critical pipelines and SLAs.",
      slack_channel: "#revenue-ops",
      on_call: "Alice Chen",
      dataset_count: 5,
      member_count: 4,
    },
    {
      id: "team-002",
      name: "Customer Insights",
      description: "Behavioral analytics and lifecycle reporting.",
      slack_channel: "#customer-insights",
      on_call: "Bob Smith",
      dataset_count: 3,
      member_count: 3,
    },
    {
      id: "team-003",
      name: "Platform Reliability",
      description: "Monitors data platform performance and cost.",
      slack_channel: "#platform-reliability",
      on_call: "Carol Johnson",
      dataset_count: 4,
      member_count: 5,
    },
  ];
}
