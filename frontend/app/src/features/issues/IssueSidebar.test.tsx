import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import type { IssueResponse } from "@/lib/api/issues";
import type { OrgRole } from "@/lib/auth/types";
import { stubApi, stubRadixDom, type StubResponse } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueSidebar } from "./IssueSidebar";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const ISSUE_URL = "/api/v1/issues/issue-1";

const baseIssue: IssueResponse = {
  id: "issue-1",
  number: 42,
  title: "Completed orders dropped ~30%",
  description: null,
  status: "triaged",
  priority: "P1",
  severity: "high",
  dataset_id: "analytics.public.orders",
  due_at: null,
  assignee_user_id: null,
  acknowledged_by: null,
  created_by_user_id: "user-2",
  author_type: "human",
  source_provider: null,
  source_external_id: null,
  source_external_url: null,
  resolution_note: null,
  context: { observed_at: "2026-09-14", column: "status" },
  labels: ["orders"],
  allowed_transitions: ["in_progress", "blocked", "closed"],
  transition_requirements: {
    in_progress: ["assignee_user_id"],
    blocked: ["assignee_user_id"],
  },
  created_at: "2026-09-14T08:02:00Z",
  updated_at: "2026-09-14T08:02:00Z",
  closed_at: null,
};

function stubSidebar(patch: StubResponse | ((b: unknown) => StubResponse)) {
  return stubApi({
    "GET /api/v1/users/": {
      body: {
        users: [
          {
            id: "user-1",
            email: "maya@acme.test",
            name: "Maya Chen",
            role: "member",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          },
          {
            id: "user-2",
            email: "raj@acme.test",
            name: "Raj Patel",
            role: "member",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 2,
      },
    },
    [`GET ${ISSUE_URL}/watchers`]: {
      body: {
        items: [{ user_id: "user-2", created_at: "2026-09-14T08:02:00Z" }],
        total: 1,
      },
    },
    [`PATCH ${ISSUE_URL}`]:
      typeof patch === "function" ? (req) => patch(req.body) : patch,
  });
}

function renderSidebar(role: OrgRole, issue: IssueResponse = baseIssue) {
  return renderAsRole(<IssueSidebar issue={issue} />, role);
}

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("IssueSidebar status", () => {
  it("offers only the allowed moves", async () => {
    stubSidebar({ body: baseIssue });
    const user = userEvent.setup();
    renderSidebar("member");

    await user.click(
      await screen.findByRole("button", { name: /Change status/ }),
    );

    const items = await screen.findAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "In Progress",
      "Blocked",
      "Closed",
    ]);
    expect(
      screen.queryByRole("menuitem", { name: "Resolved" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "Open" }),
    ).not.toBeInTheDocument();
  });

  it("asks for an assignee and sends it with the move", async () => {
    const api = stubSidebar((body) => ({
      body: {
        ...baseIssue,
        ...(body as object),
        allowed_transitions: ["blocked", "resolved", "closed"],
        transition_requirements: { resolved: ["resolution_note"] },
      },
    }));
    const user = userEvent.setup();
    renderSidebar("member");

    await user.click(
      await screen.findByRole("button", { name: /Change status/ }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "In Progress" }),
    );

    expect(api.find("PATCH", ISSUE_URL)).toHaveLength(0);
    expect(
      screen.getByText("In Progress needs an owner. Assign it to yourself?"),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "Assign to me and move to In Progress",
      }),
    );

    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      status: "in_progress",
      assignee_user_id: "user-1",
    });
  });

  it("asks for a resolution note before resolving", async () => {
    const issue: IssueResponse = {
      ...baseIssue,
      status: "in_progress",
      assignee_user_id: "user-1",
      allowed_transitions: ["blocked", "resolved", "closed"],
      transition_requirements: { resolved: ["resolution_note"] },
    };
    const api = stubSidebar({ body: { ...issue, status: "resolved" } });
    const user = userEvent.setup();
    renderSidebar("member", issue);

    await user.click(
      await screen.findByRole("button", { name: /Change status/ }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Resolved" }));

    const move = screen.getByRole("button", { name: "Move to Resolved" });
    expect(move).toBeDisabled();
    await user.click(screen.getByLabelText("Resolution note"));
    await user.paste("app_v2 wrote COMPLETE; backfilled.");
    await user.click(move);

    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      status: "resolved",
      resolution_note: "app_v2 wrote COMPLETE; backfilled.",
    });
  });

  it("pre-fills the resolution note from the confirmed root cause", async () => {
    const issue: IssueResponse = {
      ...baseIssue,
      status: "in_progress",
      assignee_user_id: "user-1",
      allowed_transitions: ["blocked", "resolved", "closed"],
      // A confirmed, synthesized run means the server needs no note...
      transition_requirements: {},
    };
    const api = stubApi({
      "GET /api/v1/users/": { body: { users: [], total: 0 } },
      [`GET ${ISSUE_URL}/watchers`]: { body: { items: [], total: 0 } },
      [`GET ${ISSUE_URL}/investigation-runs`]: {
        body: {
          items: [
            {
              id: "run-1",
              investigation_id: "inv-1",
              synthesis_summary: "app_v2 writes COMPLETE instead of completed",
              outcome_verdict: "confirmed",
              outcome_reviewed_at: "2026-09-14T08:50:00Z",
            },
          ],
          total: 1,
        },
      },
      [`PATCH ${ISSUE_URL}`]: { body: { ...issue, status: "resolved" } },
    });
    const user = userEvent.setup();
    renderSidebar("member", issue);

    await waitFor(() =>
      expect(api.find("GET", `${ISSUE_URL}/investigation-runs`)).toHaveLength(
        1,
      ),
    );
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    await user.click(
      await screen.findByRole("button", { name: /Change status/ }),
    );
    // ...but the person still sees the note, pre-filled, before resolving.
    await user.click(await screen.findByRole("menuitem", { name: "Resolved" }));
    expect(screen.getByLabelText("Resolution note")).toHaveValue(
      "app_v2 writes COMPLETE instead of completed",
    );
    await user.click(screen.getByLabelText("Resolution note"));
    await user.paste("; backfilled");
    await user.click(screen.getByRole("button", { name: "Move to Resolved" }));

    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      status: "resolved",
      resolution_note:
        "app_v2 writes COMPLETE instead of completed; backfilled",
    });
  });

  it("shows the server's message when a change fails", async () => {
    stubSidebar({
      status: 400,
      body: { detail: "Cannot transition from triaged to closed" },
    });
    const user = userEvent.setup();
    renderSidebar("member");

    await user.click(
      await screen.findByRole("button", { name: /Change status/ }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Closed" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Couldn't move the issue to Closed",
        { description: "Cannot transition from triaged to closed" },
      ),
    );
  });

  it("keeps viewers read-only", async () => {
    stubSidebar({ body: baseIssue });
    renderSidebar("viewer");

    expect(await screen.findByText("Raj Patel")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Change status/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Priority")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Add label")).not.toBeInTheDocument();
  });
});

describe("IssueSidebar details", () => {
  it("shows where the problem was seen", async () => {
    stubSidebar({ body: baseIssue });
    renderSidebar("member");

    expect(await screen.findByText("2026-09-14")).toBeInTheDocument();
    expect(screen.getByText("status")).toBeInTheDocument();
    // Watchers by name, not id.
    expect(await screen.findByText("Raj Patel")).toBeInTheDocument();
  });

  it("changes priority inline", async () => {
    const api = stubSidebar({ body: { ...baseIssue, priority: "P0" } });
    const user = userEvent.setup();
    renderSidebar("member");

    await user.click(await screen.findByLabelText("Priority"));
    await user.click(await screen.findByRole("option", { name: "P0" }));

    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({ priority: "P0" });
  });

  it("assigns by name and can clear the assignee", async () => {
    const api = stubSidebar((body) => ({
      body: { ...baseIssue, ...(body as object) },
    }));
    const user = userEvent.setup();
    renderSidebar("member", { ...baseIssue, assignee_user_id: "user-2" });

    const trigger = await screen.findByLabelText("Assignee");
    await waitFor(() => expect(trigger).toHaveTextContent("Raj Patel"));

    await user.click(trigger);
    await user.click(await screen.findByRole("option", { name: "Unassigned" }));

    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      assignee_user_id: null,
    });
  });

  it("adds and removes labels", async () => {
    const api = stubSidebar((body) => ({
      body: { ...baseIssue, ...(body as object) },
    }));
    const user = userEvent.setup();
    renderSidebar("member");

    await user.click(await screen.findByRole("textbox", { name: "Add label" }));
    await user.paste("App_V2");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(1));
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      labels: ["orders", "app_v2"],
    });

    await user.click(
      screen.getByRole("button", { name: "Remove label orders" }),
    );
    await waitFor(() => expect(api.find("PATCH", ISSUE_URL)).toHaveLength(2));
    expect(api.find("PATCH", ISSUE_URL)[1].body).toEqual({ labels: [] });
  });
});
