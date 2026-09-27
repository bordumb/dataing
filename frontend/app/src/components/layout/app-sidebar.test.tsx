import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { SidebarProvider } from "@/components/ui/sidebar";
import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { AppSidebar } from "./app-sidebar";

vi.mock("@/lib/notifications", () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}));

vi.mock("@/lib/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/api")>()),
  getUserOrgs: async () => [],
}));

function renderSidebar(role: OrgRole) {
  return renderAsRole(
    <SidebarProvider>
      <AppSidebar />
    </SidebarProvider>,
    role,
  );
}

afterEach(() => localStorage.clear());

describe("AppSidebar", () => {
  it("does not offer viewers the new investigation shortcut", async () => {
    renderSidebar("viewer");

    expect(await screen.findByText("Platform")).toBeInTheDocument();
    expect(screen.queryByText("New Investigation")).not.toBeInTheDocument();
  });

  it("offers members the new investigation shortcut", async () => {
    renderSidebar("member");

    expect(await screen.findByText("New Investigation")).toBeInTheDocument();
  });

  it.each(["viewer", "member"] as const)(
    "does not show %s users the admin link",
    async (role) => {
      renderSidebar(role);

      expect(
        await screen.findByRole("link", { name: "Settings" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Admin" }),
      ).not.toBeInTheDocument();
    },
  );

  it("shows admins the admin link", async () => {
    renderSidebar("admin");

    expect(
      await screen.findByRole("link", { name: "Admin" }),
    ).toBeInTheDocument();
  });
});
