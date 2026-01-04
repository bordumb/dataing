import { useCallback } from "react";
import { getCurrentUser } from "@/lib/api/users";
import { useUserStore } from "@/lib/stores/user-store";
import { Permission, ROLE_PERMISSIONS } from "@/lib/auth/roles";

export function usePermissions() {
  const { user, viewAsRole, setViewAsRole } = useUserStore();
  const effectiveRole = viewAsRole ?? user?.role ?? "viewer";

  const hasPermission = useCallback(
    (permission: Permission) => ROLE_PERMISSIONS[effectiveRole]?.includes(permission) ?? false,
    [effectiveRole],
  );

  return {
    effectiveRole,
    actualRole: user?.role,
    hasPermission,
    setViewAsRole,
  };
}

export async function requirePermission(permission: Permission) {
  const user = await getCurrentUser();
  const allowed = ROLE_PERMISSIONS[user.role]?.includes(permission) ?? false;
  if (!allowed) {
    throw new Error("Insufficient permissions");
  }
}
