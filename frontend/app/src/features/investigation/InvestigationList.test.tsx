import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { stubApi, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";
import { InvestigationList } from "./InvestigationList";

vi.mock("@/lib/api/investigations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/investigations")>()),
  useInvestigations: () => ({
    data: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("InvestigationList", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    renderAsRole(<InvestigationList />, "viewer");

    expect(
      await screen.findByText("No investigations yet."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Investigate…")).not.toBeInTheDocument();
  });

  it.each([
    ["the header", 0],
    ["the empty state", 1],
  ])("opens the brief editor from %s", async (_where, index) => {
    stubApi({ "GET /api/v1/datasources": { body: { items: [], total: 0 } } });
    renderAsRole(<InvestigationList />, "member");

    const buttons = await screen.findAllByRole("button", {
      name: "Investigate…",
    });
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[index]);

    expect(
      await screen.findByRole("dialog", { name: "Start an investigation" }),
    ).toBeInTheDocument();
  });
});
