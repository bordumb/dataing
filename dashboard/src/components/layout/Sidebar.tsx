"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Book,
  Building2,
  Database,
  Home,
  LineChart,
  Plug,
  Search,
  User,
  Users,
} from "lucide-react";
import { TeamSelector } from "@/components/teams/TeamSelector";
import { usePermissions } from "@/lib/auth/permissions";
import { Permission } from "@/lib/auth/roles";
import type { Team } from "@/types/team";
import type { User as UserType } from "@/types/user";

interface SidebarProps {
  user?: UserType | null;
  currentTeam?: Team | null;
  userTeams?: Team[];
}

const navSections = [
  {
    title: "Investigate",
    items: [
      { href: "/home", label: "Home", icon: Home },
      { href: "/investigations", label: "Investigations", icon: Search },
      { href: "/datasets", label: "Datasets", icon: Database },
    ],
  },
  {
    title: "Insights",
    items: [
      { href: "/analytics", label: "Analytics", icon: LineChart },
      { href: "/knowledge", label: "Knowledge Base", icon: Book },
    ],
  },
  {
    title: "Operations",
    items: [{ href: "/integrations", label: "Integrations", icon: Plug }],
  },
];

const adminItems = {
  title: "Admin",
  items: [
    { href: "/org", label: "Organization", icon: Building2 },
    { href: "/teams", label: "Teams", icon: Users },
    { href: "/users", label: "Users", icon: User },
  ],
};

export function Sidebar({ currentTeam, userTeams }: SidebarProps) {
  const pathname = usePathname();
  const { hasPermission } = usePermissions();

  return (
    <aside className="sticky top-0 hidden h-screen w-64 flex-col gap-6 overflow-y-auto border-r border-border bg-background-elevated/80 px-4 py-6 lg:flex">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <span className="h-8 w-8 rounded-lg bg-primary text-center text-sm font-bold leading-8 text-primary-foreground">
          D
        </span>
        DataDr
      </div>

      <TeamSelector
        initialTeam={currentTeam ?? undefined}
        availableTeams={userTeams}
      />

      <div className="space-y-5">
        {navSections.map((section) => (
          <NavSection key={section.title} title={section.title}>
            {section.items.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                icon={item.icon}
                active={pathname.startsWith(item.href)}
              >
                {item.label}
              </NavLink>
            ))}
          </NavSection>
        ))}

        {hasPermission(Permission.ORG_ADMIN) && (
          <NavSection title={adminItems.title}>
            {adminItems.items.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                icon={item.icon}
                active={pathname.startsWith(item.href)}
              >
                {item.label}
              </NavLink>
            ))}
          </NavSection>
        )}
      </div>
    </aside>
  );
}

function NavSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function NavLink({
  href,
  icon: Icon,
  children,
  active,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
        active ? "bg-primary text-primary-foreground" : "text-foreground-muted hover:bg-background-subtle hover:text-foreground"
      }`}
    >
      <Icon className="h-4 w-4" />
      {children}
    </Link>
  );
}
