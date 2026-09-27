import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { IssueWorkspace } from "./IssueWorkspace";

vi.mock("@/lib/api/issues", async (importOriginal) => {
  const query = (data: unknown) => () => ({
    data,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  const mutation = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  });
  const emptyList = { items: [], total: 0 };
  return {
    ...(await importOriginal<typeof import("@/lib/api/issues")>()),
    useIssue: query({
      id: "issue-1",
      number: 7,
      title: "Null spike in orders.email",
      description: null,
      status: "open",
      priority: null,
      severity: null,
      dataset_id: null,
      assignee_user_id: null,
      labels: [],
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      closed_at: null,
    }),
    useIssueComments: query(emptyList),
    useIssueWatchers: query(emptyList),
    useIssueInvestigationRuns: query(emptyList),
    useUpdateIssue: mutation,
    useCreateIssueComment: mutation,
    useWatchIssue: mutation,
    useUnwatchIssue: mutation,
    useSpawnInvestigation: mutation,
    useInvalidateIssues: () => new Proxy({}, { get: () => vi.fn() }),
  };
});

function renderWorkspace(role: OrgRole) {
  return renderAsRole(
    <Routes>
      <Route path="/issues/:id" element={<IssueWorkspace />} />
    </Routes>,
    role,
    "/issues/issue-1",
  );
}

afterEach(() => localStorage.clear());

describe("IssueWorkspace", () => {
  it("keeps viewers to watching and commenting", async () => {
    renderWorkspace("viewer");

    expect(
      await screen.findByText("Null spike in orders.email"),
    ).toBeInTheDocument();
    expect(screen.getByText("Watch")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Add a comment...")).toBeInTheDocument();
    expect(screen.queryByText("Run Investigation")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Open"));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("lets members run investigations and change status", async () => {
    renderWorkspace("member");

    expect(await screen.findByText("Run Investigation")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Open"));
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });
});
