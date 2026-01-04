import { Button } from "@/components/ui/Button";
import { UserTable } from "@/components/admin/UserTable";
import { requirePermission } from "@/lib/auth/permissions";
import { Permission } from "@/lib/auth/roles";
import { getUsers } from "@/lib/api/users";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function UsersPage() {
  await requirePermission(Permission.USER_MANAGE);
  const users = await getUsers();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="section-title text-3xl font-semibold">Users</h1>
        <Button variant="outline">Invite User</Button>
      </div>
      <UserTable users={users} />
    </div>
  );
}
