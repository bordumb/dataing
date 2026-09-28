import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubApi, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";
import { IssueWorkspace } from "./IssueWorkspace";

const ISSUE_URL = "/api/v1/issues/issue-1";

function stubWorkspace() {
  const empty = { body: { items: [], total: 0 } };
  return stubApi({
    [`GET ${ISSUE_URL}`]: {
      body: {
        id: "issue-1",
        number: 7,
        title: "Null spike in orders.email",
        description: "Nulls **jumped** after the deploy.",
        status: "open",
        priority: null,
        severity: null,
        dataset_id: null,
        due_at: null,
        assignee_user_id: null,
        acknowledged_by: null,
        created_by_user_id: null,
        author_type: "human",
        source_provider: null,
        source_external_id: null,
        source_external_url: null,
        resolution_note: null,
        context: {},
        labels: [],
        allowed_transitions: ["triaged", "in_progress", "closed"],
        transition_requirements: { in_progress: ["assignee_user_id"] },
        created_at: "2026-09-01T00:00:00Z",
        updated_at: "2026-09-01T00:00:00Z",
        closed_at: null,
      },
    },
    "GET /api/v1/users/": { body: { users: [], total: 0 } },
    [`GET ${ISSUE_URL}/watchers`]: empty,
    [`GET ${ISSUE_URL}/investigation-runs`]: empty,
    [`GET ${ISSUE_URL}/threads`]: {
      body: {
        items: [
          {
            id: "thread-1",
            issue_id: "issue-1",
            kind: "shared",
            owner_user_id: null,
            title: null,
            created_at: "2026-09-01T00:00:00Z",
          },
        ],
      },
    },
    [`GET ${ISSUE_URL}/threads/thread-1/messages`]: { body: { items: [] } },
  });
}

function renderWorkspace(role: OrgRole) {
  stubWorkspace();
  vi.stubGlobal("EventSource", FakeEventSource);
  return renderAsRole(
    <Routes>
      <Route path="/issues/:id" element={<IssueWorkspace />} />
    </Routes>,
    role,
    "/issues/issue-1",
  );
}

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("IssueWorkspace", () => {
  it("keeps viewers to watching and commenting", async () => {
    renderWorkspace("viewer");

    expect(
      await screen.findByText("Null spike in orders.email"),
    ).toBeInTheDocument();
    expect(screen.getByText("jumped").tagName).toBe("STRONG");
    expect(await screen.findByText("Watch")).toBeInTheDocument();
    expect(
      await screen.findByPlaceholderText(
        "Write a comment for the team (Markdown)",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Run Investigation")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Change status/ }),
    ).not.toBeInTheDocument();
  });

  it("lets members run investigations and change status", async () => {
    renderWorkspace("member");

    expect(await screen.findByText("Run Investigation")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Change status/ }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Ask agent" }),
    ).toBeEnabled();
  });
});
