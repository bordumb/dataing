import { api, API_BASE_URL } from "./client";
import type { User, UserActivity, APIKey, UserPreferences } from "@/types/user";
import type { Team } from "@/types/team";

interface APIUser {
  id: string;
  name: string;
  email: string;
  role: string;
  investigation_count: number;
  created_at: string | null;
}

interface UserProfileResponse {
  id: string;
  name: string;
  email: string;
  organization_id: string | null;
  role: string;
  created_at: string;
  preferences: Record<string, unknown> | null;
}

interface UserActivityResponse {
  activity: Array<{
    id: string;
    activity_type: string;
    resource_type: string;
    resource_id: string | null;
    timestamp: string;
    metadata: Record<string, unknown> | null;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface APIKeyListResponse {
  api_keys: Array<{
    id: string;
    name: string;
    prefix: string;
    scopes: string[];
    created_at: string;
    expires_at: string | null;
    last_used_at: string | null;
    is_active: boolean;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface APIKeyCreatedResponse {
  id: string;
  name: string;
  secret: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
}

export async function getUsers(): Promise<User[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/users`);
    if (!response.ok) {
      throw new Error(`Failed to fetch users: ${response.statusText}`);
    }
    const data: { users: APIUser[] } = await response.json();

    return data.users.map((user) => ({
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role as "admin" | "member" | "viewer",
      roles: [user.role as "admin" | "member" | "viewer"],
      teams: [],
      last_active_at: user.created_at || undefined,
      stats: {
        investigations_triggered: user.investigation_count,
        approvals_given: 0,
        knowledge_entries: 0,
      },
    }));
  } catch (error) {
    console.error("Error fetching users:", error);
    return [];
  }
}

export async function getUser(userId: string): Promise<User> {
  const users = await getUsers();
  const user = users.find((item) => item.id === userId);
  if (!user) {
    throw new Error("User not found");
  }
  return user;
}

export async function getCurrentUser(): Promise<User> {
  try {
    const data = await api.get<UserProfileResponse>("/api/v1/users/me");
    return {
      id: data.id,
      name: data.name,
      email: data.email,
      role: data.role as "admin" | "member" | "viewer",
      roles: [data.role as "admin" | "member" | "viewer"],
      teams: [],
      preferences: data.preferences as UserPreferences | undefined,
      stats: {
        investigations_triggered: 0,
        approvals_given: 0,
        knowledge_entries: 0,
      },
    };
  } catch (error) {
    console.error("Error fetching current user:", error);
    // Fallback to users list
    const users = await getUsers();
    const adminUser = users.find((u) => u.role === "admin");
    if (adminUser) return adminUser;
    if (users.length > 0) return users[0];

    // Return fallback user
    return {
      id: "demo-user",
      name: "Demo User",
      email: "demo@acme.demo",
      role: "admin",
      roles: ["admin"],
      teams: [],
      stats: {
        investigations_triggered: 0,
        approvals_given: 0,
        knowledge_entries: 0,
      },
    };
  }
}

export async function updateCurrentUser(data: {
  name?: string;
  preferences?: UserPreferences;
}): Promise<User> {
  const response = await api.post<UserProfileResponse>("/api/v1/users/me", data);
  return {
    id: response.id,
    name: response.name,
    email: response.email,
    role: response.role as "admin" | "member" | "viewer",
    roles: [response.role as "admin" | "member" | "viewer"],
    teams: [],
    preferences: response.preferences as UserPreferences | undefined,
    stats: {
      investigations_triggered: 0,
      approvals_given: 0,
      knowledge_entries: 0,
    },
  };
}

export async function getUserActivity(
  userId: string,
  params?: { limit?: number; offset?: number }
): Promise<{
  activity: UserActivity[];
  total: number;
  has_more: boolean;
}> {
  try {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.set("limit", String(params.limit));
    if (params?.offset) queryParams.set("offset", String(params.offset));

    const response = await api.get<UserActivityResponse>(
      `/api/v1/users/${userId}/activity?${queryParams}`
    );

    return {
      activity: response.activity.map((a) => ({
        id: a.id,
        activity_type: a.activity_type,
        resource_type: a.resource_type,
        resource_id: a.resource_id || undefined,
        timestamp: a.timestamp,
        metadata: a.metadata || undefined,
      })),
      total: response.meta.total,
      has_more: response.meta.has_more,
    };
  } catch (error) {
    console.error("Error fetching user activity:", error);
    return { activity: [], total: 0, has_more: false };
  }
}

export async function getUserTeams(userId: string): Promise<Team[]> {
  // This would typically be fetched from a user-teams endpoint
  // For now, return empty array
  return [];
}

// API Keys Management
export async function getAPIKeys(): Promise<APIKey[]> {
  try {
    const response = await api.get<APIKeyListResponse>("/api/v1/users/me/api-keys");
    return response.api_keys.map((key) => ({
      id: key.id,
      name: key.name,
      prefix: key.prefix,
      scopes: key.scopes,
      created_at: key.created_at,
      expires_at: key.expires_at || undefined,
      last_used_at: key.last_used_at || undefined,
      is_active: key.is_active,
    }));
  } catch (error) {
    console.error("Error fetching API keys:", error);
    return [];
  }
}

export async function createAPIKey(data: {
  name: string;
  scopes?: string[];
  expires_in_days?: number;
}): Promise<{
  id: string;
  name: string;
  secret: string;
  scopes: string[];
  created_at: string;
  expires_at?: string;
}> {
  const response = await api.post<APIKeyCreatedResponse>("/api/v1/users/me/api-keys", {
    name: data.name,
    scopes: data.scopes || ["read", "write"],
    expires_in_days: data.expires_in_days,
  });

  return {
    id: response.id,
    name: response.name,
    secret: response.secret,
    scopes: response.scopes,
    created_at: response.created_at,
    expires_at: response.expires_at || undefined,
  };
}

export async function revokeAPIKey(keyId: string): Promise<void> {
  await api.delete(`/api/v1/users/me/api-keys/${keyId}`);
}
