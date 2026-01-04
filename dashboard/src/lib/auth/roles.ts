import type { UserRole } from "@/types/user";

export enum Permission {
  ORG_ADMIN = "org:admin",
  USER_MANAGE = "user:manage",
  TEAM_ADMIN = "team:admin",
  INVESTIGATION_TRIGGER = "investigation:trigger",
  VIEW_BILLING = "billing:view",
}

export const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  admin: [
    Permission.ORG_ADMIN,
    Permission.USER_MANAGE,
    Permission.TEAM_ADMIN,
    Permission.INVESTIGATION_TRIGGER,
    Permission.VIEW_BILLING,
  ],
  member: [Permission.TEAM_ADMIN, Permission.INVESTIGATION_TRIGGER],
  viewer: [],
};
