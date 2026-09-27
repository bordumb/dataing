import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderAsRole } from "@/test/auth";
import { IssueList } from "./IssueList";

vi.mock("@/lib/api/issues", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/issues")>()),
  useIssues: () => ({
    data: { items: [], next_cursor: null },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

afterEach(() => localStorage.clear());

describe("IssueList", () => {
  it("does not offer viewers a way to create an issue", async () => {
    renderAsRole(<IssueList />, "viewer");

    expect(await screen.findByText("No issues found.")).toBeInTheDocument();
    expect(screen.queryByText("New Issue")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Create your first issue"),
    ).not.toBeInTheDocument();
  });

  it("offers members a way to create an issue", async () => {
    renderAsRole(<IssueList />, "member");

    expect(await screen.findByText("New Issue")).toBeInTheDocument();
    expect(screen.getByText("Create your first issue")).toBeInTheDocument();
  });
});
