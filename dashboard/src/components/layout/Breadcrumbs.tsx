"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const labelMap: Record<string, string> = {
  home: "Home",
  org: "Organization",
  users: "Users",
  teams: "Teams",
  investigations: "Investigations",
  datasets: "Datasets",
  analytics: "Analytics",
  integrations: "Integrations",
  knowledge: "Knowledge",
  profile: "Profile",
};

export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const crumbs = segments.map((segment, index) => {
    const href = "/" + segments.slice(0, index + 1).join("/");
    const label = labelMap[segment] ?? segment.replace(/-/g, " ");
    return { href, label };
  });

  if (crumbs.length === 0) return null;

  return (
    <nav className="text-sm text-foreground-muted">
      <ol className="flex flex-wrap items-center gap-2">
        {crumbs.map((crumb, index) => (
          <li key={crumb.href} className="flex items-center gap-2">
            {index > 0 && <span className="text-foreground-muted/50">/</span>}
            <Link href={crumb.href} className="hover:text-foreground">
              {crumb.label}
            </Link>
          </li>
        ))}
      </ol>
    </nav>
  );
}
