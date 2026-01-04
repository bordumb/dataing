"use client";

import { useState } from "react";
import { DataTable } from "@/components/common/DataTable";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { RoleEditor } from "@/components/admin/RoleEditor";
import { Can } from "@/lib/auth/Can";
import { Permission } from "@/lib/auth/roles";
import { formatRelative } from "@/lib/utils/formatters";
import type { User } from "@/types/user";

export function UserTable({ users }: { users: User[] }) {
  const [localUsers, setLocalUsers] = useState(users);

  return (
    <DataTable
      data={localUsers}
      searchKeys={["name", "email"]}
      filterOptions={[
        { key: "role", label: "Role", options: ["admin", "member", "viewer"] },
      ]}
      columns={[
        {
          key: "name",
          label: "Name",
          render: (user) => (
            <div className="flex items-center gap-3">
              <Avatar src={user.avatar_url} name={user.name} size="sm" />
              <div>
                <p className="text-sm font-semibold text-foreground">{user.name}</p>
                <p className="text-xs text-foreground-muted">{user.email}</p>
              </div>
            </div>
          ),
        },
        {
          key: "teams",
          label: "Teams",
          render: (user) => user.teams.map((team) => team.name).join(", "),
        },
        {
          key: "role",
          label: "Role",
          render: (user) => <Badge variant="outline">{user.role}</Badge>,
        },
        {
          key: "last_active_at",
          label: "Last Active",
          render: (user) => (user.last_active_at ? formatRelative(user.last_active_at) : "-") ,
        },
        {
          key: "actions",
          label: "",
          render: (user) => (
            <Can permission={Permission.USER_MANAGE}>
              <RoleEditor
                currentRole={user.role}
                onSave={(role) => {
                  setLocalUsers((prev) => prev.map((entry) => (entry.id === user.id ? { ...entry, role } : entry)));
                }}
                trigger={<Button variant="ghost" size="sm">Edit</Button>}
              />
            </Can>
          ),
        },
      ]}
    />
  );
}
