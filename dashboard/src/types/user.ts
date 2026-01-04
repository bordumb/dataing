export type UserRole = "admin" | "member" | "viewer";

export interface UserTeamSummary {
  id: string;
  name: string;
}

export interface UserStats {
  investigations_triggered: number;
  approvals_given: number;
  knowledge_entries: number;
}

export interface UserPreferences {
  theme?: "light" | "dark" | "system";
  notifications?: {
    email?: boolean;
    slack?: boolean;
    in_app?: boolean;
  };
  default_team_id?: string;
  timezone?: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  roles: UserRole[];
  avatar_url?: string;
  teams: UserTeamSummary[];
  last_active_at?: string;
  stats: UserStats;
  preferences?: UserPreferences;
}

export interface UserActivity {
  id: string;
  description?: string;
  activity_type: string;
  resource_type: string;
  resource_id?: string;
  timestamp: string;
  created_at?: string;
  type?: "investigation" | "approval" | "note" | "login";
  metadata?: Record<string, unknown>;
}

export interface APIKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
  is_active: boolean;
}
