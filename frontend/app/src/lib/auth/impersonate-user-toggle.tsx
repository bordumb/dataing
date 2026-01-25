/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Admin impersonation toggle for testing multi-user features.
 * Only visible to admin users in demo/development mode.
 *
 * Displays in the header next to the mode toggle.
 */

import { UserCircle, ChevronDown, LogOut, Check } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/Badge";
import { useImpersonation, type DemoUser } from "./impersonation-context";

const ROLE_COLORS: Record<string, string> = {
  viewer: "bg-gray-100 text-gray-700",
  member: "bg-blue-100 text-blue-700",
  admin: "bg-amber-100 text-amber-700",
};

function UserItem({
  user,
  isSelected,
}: {
  user: DemoUser;
  isSelected: boolean;
}) {
  return (
    <div className="flex items-center justify-between w-full">
      <div className="flex flex-col">
        <span className="font-medium">{user.name}</span>
        <span className="text-xs text-muted-foreground">{user.email}</span>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={ROLE_COLORS[user.role]}>
          {user.role}
        </Badge>
        {isSelected && <Check className="h-4 w-4 text-green-500" />}
      </div>
    </div>
  );
}

/**
 * CRITICAL: DO NOT REMOVE THIS COMPONENT
 *
 * Renders a "Login as" dropdown for admin user impersonation.
 * Only visible in development mode and when user is admin.
 */
export function ImpersonateUserToggle() {
  const {
    currentUser,
    isImpersonating,
    impersonate,
    stopImpersonating,
    canImpersonate,
    availableUsers,
  } = useImpersonation();

  // Only show in development and if user can impersonate
  if (import.meta.env.PROD) return null;
  if (!canImpersonate) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={isImpersonating ? "destructive" : "outline"}
          size="sm"
          className="gap-2"
        >
          <UserCircle className="h-4 w-4" />
          <span className="max-w-[100px] truncate">
            {isImpersonating ? `As ${currentUser.name}` : currentUser.name}
          </span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Login as User</span>
          {isImpersonating && (
            <Button
              variant="ghost"
              size="sm"
              onClick={stopImpersonating}
              className="h-6 text-xs gap-1"
            >
              <LogOut className="h-3 w-3" />
              Stop
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={currentUser.id}
          onValueChange={impersonate}
        >
          {availableUsers.map((user) => (
            <DropdownMenuRadioItem
              key={user.id}
              value={user.id}
              className="cursor-pointer py-2"
            >
              <UserItem user={user} isSelected={currentUser.id === user.id} />
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <div className="px-2 py-1.5 text-xs text-muted-foreground">
          Use this to test how different users experience investigations
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
