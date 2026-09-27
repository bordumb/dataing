import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderAsRole } from "@/test/auth";
import { DashboardPage } from "./dashboard-page";

vi.mock("@/lib/api/dashboard", () => ({
  fetchDashboardStats: async () => ({
    activeInvestigations: 0,
    completedToday: 0,
    dataSources: 1,
    pendingApprovals: 0,
  }),
}));

vi.mock("@/lib/api/investigations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/investigations")>()),
  useInvestigations: () => ({ data: [], isLoading: false, error: null }),
}));

afterEach(() => localStorage.clear());

describe("DashboardPage", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    renderAsRole(<DashboardPage />, "viewer");

    expect(
      await screen.findByText("No investigations yet"),
    ).toBeInTheDocument();
    expect(screen.queryByText("New Investigation")).not.toBeInTheDocument();
    expect(screen.queryByText("Create Investigation")).not.toBeInTheDocument();
  });

  it("offers members a way to start an investigation", async () => {
    renderAsRole(<DashboardPage />, "member");

    expect(await screen.findByText("New Investigation")).toBeInTheDocument();
    expect(screen.getByText("Create Investigation")).toBeInTheDocument();
  });
});
