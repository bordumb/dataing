import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SidebarProvider } from "@/components/ui/sidebar";
import type { OrgRole } from "@/lib/auth/types";
import { stubApi, stubRadixDom } from "@/test/api";
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

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("AppSidebar", () => {
  it("does not offer viewers the Investigate… shortcut", async () => {
    renderSidebar("viewer");

    expect(await screen.findByText("Platform")).toBeInTheDocument();
    expect(screen.queryByText("Investigate…")).not.toBeInTheDocument();
  });

  it("opens the brief editor from the Investigate… shortcut", async () => {
    stubApi({ "GET /api/v1/datasources": { body: { items: [], total: 0 } } });
    renderSidebar("member");

    await userEvent.click(
      await screen.findByRole("button", { name: "Investigate…" }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Start an investigation" }),
    ).toBeInTheDocument();
    // No page links to the removed /investigations/new.
    expect(
      document.querySelector('a[href="/investigations/new"]'),
    ).not.toBeInTheDocument();
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
