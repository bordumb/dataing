"use client";

import { DropdownMenu, DropdownTrigger, DropdownContent, DropdownItem } from "@/components/ui/DropdownMenu";
import { usePermissions } from "@/lib/auth/permissions";

export function RoleSwitcher() {
  const { effectiveRole, actualRole, setViewAsRole } = usePermissions();

  if (actualRole !== "admin") return null;

  return (
    <DropdownMenu>
      <DropdownTrigger>
        Viewing as: {effectiveRole === "admin" ? "Admin" : "User"}
      </DropdownTrigger>
      <DropdownContent>
        <DropdownItem onClick={() => setViewAsRole("admin")}>Admin View</DropdownItem>
        <DropdownItem onClick={() => setViewAsRole("member")}>Member View</DropdownItem>
        <DropdownItem onClick={() => setViewAsRole("viewer")}>Viewer View</DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}
