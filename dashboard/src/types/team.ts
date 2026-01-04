export interface Team {
  id: string;
  name: string;
  description: string;
  member_count: number;
  dataset_count: number;
  lead?: string;
  slack_channel?: string;
  on_call?: string;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
  avatar_url?: string;
}

export interface TeamStats {
  active_investigations: number;
  anomalies_30d: number;
  mttr_hours: number;
  sla_pct: number;
}
