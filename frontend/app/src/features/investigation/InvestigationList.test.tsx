import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

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

afterEach(() => localStorage.clear());

describe("InvestigationList", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    renderAsRole(<InvestigationList />, "viewer");

    expect(
      await screen.findByText("No investigations yet."),
    ).toBeInTheDocument();
    expect(screen.queryByText("New Investigation")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Create your first investigation"),
    ).not.toBeInTheDocument();
  });

  it("offers members a way to start an investigation", async () => {
    renderAsRole(<InvestigationList />, "member");

    expect(await screen.findByText("New Investigation")).toBeInTheDocument();
    expect(
      screen.getByText("Create your first investigation"),
    ).toBeInTheDocument();
  });
});
