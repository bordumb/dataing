"use client";

import { Bell, ChevronDown } from "lucide-react";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { RoleSwitcher } from "@/components/layout/RoleSwitcher";
import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";
import { Avatar } from "@/components/ui/Avatar";
import { DropdownMenu, DropdownTrigger, DropdownContent, DropdownItem } from "@/components/ui/DropdownMenu";
import { useUserStore } from "@/lib/stores/user-store";

export function Header() {
  const user = useUserStore((state) => state.user);

  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-4 border-b border-border bg-background-elevated/80 px-6 py-4 backdrop-blur">
      <CommandPalette />

      <div className="flex items-center gap-3">
        <RoleSwitcher />
        <ThemeSwitcher />
        <button className="relative rounded-full border border-border bg-background-elevated/60 p-2 text-foreground-muted transition hover:bg-background-subtle hover:text-foreground">
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-primary" />
        </button>

        <DropdownMenu>
          <DropdownTrigger>
            <span className="flex items-center gap-2">
              <Avatar src={user?.avatar_url} name={user?.name} size="sm" />
              <span className="hidden text-sm font-semibold text-foreground md:inline">{user?.name}</span>
              <ChevronDown className="h-4 w-4 text-foreground-muted" />
            </span>
          </DropdownTrigger>
          <DropdownContent>
            <DropdownItem>Profile</DropdownItem>
            <DropdownItem>Preferences</DropdownItem>
            <DropdownItem>Sign out</DropdownItem>
          </DropdownContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
