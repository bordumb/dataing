import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { stubApi, stubRadixDom } from "@/test/api";
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

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("DashboardPage", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    renderAsRole(<DashboardPage />, "viewer");

    expect(
      await screen.findByText("No investigations yet"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Investigate…")).not.toBeInTheDocument();
  });

  it.each([
    ["the header", 0],
    ["the empty recent-investigations card", 1],
  ])("opens the brief editor from %s", async (_where, index) => {
    stubApi({ "GET /api/v1/datasources": { body: { items: [], total: 0 } } });
    renderAsRole(<DashboardPage />, "member");

    const buttons = await screen.findAllByRole("button", {
      name: "Investigate…",
    });
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[index]);

    const dialog = await screen.findByRole("dialog", {
      name: "Start an investigation",
    });
    // The dashboard knows nothing about the problem yet.
    expect(within(dialog).getByLabelText("Symptom")).toHaveValue("");
    expect(within(dialog).getByLabelText("Table")).toHaveValue("");
  });
});
