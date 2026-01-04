"use client";

import { usePermissions } from "./permissions";
import type { Permission } from "./roles";

interface CanProps {
  permission: Permission;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Permission Guard Component for RBAC
 *
 * Wraps sensitive actions and only renders children if the user has the required permission.
 *
 * @example
 * ```tsx
 * <Can permission={Permission.USER_MANAGE}>
 *   <Button>Edit User</Button>
 * </Can>
 * ```
 */
export function Can({ permission, children, fallback = null }: CanProps) {
  const { hasPermission } = usePermissions();

  if (!hasPermission(permission)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
