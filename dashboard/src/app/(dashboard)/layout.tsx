import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { KeyboardShortcuts } from "@/components/layout/KeyboardShortcuts";
import { getTeams } from "@/lib/api/teams";
import { getCurrentUser } from "@/lib/api/users";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getCurrentUser();
  const teams = await getTeams();

  return (
    <div className="flex min-h-screen">
      <Sidebar user={user} currentTeam={teams[0]} />
      <div className="flex flex-1 flex-col">
        <Header />
        <div className="px-6 pt-4">
          <Breadcrumbs />
        </div>
        <main className="flex-1 px-6 py-6">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
            {children}
          </div>
        </main>
        <KeyboardShortcuts />
      </div>
    </div>
  );
}
