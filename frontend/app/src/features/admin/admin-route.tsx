import { RoleGuard } from "@/lib/auth";
import { AdminPage } from "./admin-page";

/**
 * The /admin page, open to org admins and owners only.
 *
 * Every action on it is admin-only in the API, so anyone else is sent to
 * the dashboard instead of a page of controls that would fail with 403.
 */
export function AdminRoute() {
  return (
    <RoleGuard minRole="admin" redirectTo="/">
      <AdminPage />
    </RoleGuard>
  );
}
