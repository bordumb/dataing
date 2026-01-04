"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogTrigger, DialogClose } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import type { UserRole } from "@/types/user";

export function RoleEditor({
  currentRole,
  onSave,
  trigger,
}: {
  currentRole: UserRole;
  onSave: (role: UserRole) => void;
  trigger: React.ReactNode;
}) {
  const [role, setRole] = useState<UserRole>(currentRole);

  return (
    <Dialog>
      <DialogTrigger>{trigger}</DialogTrigger>
      <DialogContent>
        <h2 className="section-title text-lg font-semibold">Edit role</h2>
        <div className="mt-4">
          <Select label="Role" value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </Select>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <DialogClose>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            onClick={() => {
              onSave(role);
            }}
          >
            Save
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
