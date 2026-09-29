import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
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

    const change = await screen.findByRole("button", { name: /Change status/ });
    expect(change).toHaveTextContent("Change ▾");
    await user.click(change);

    const items = await screen.findAllByRole("menuitem");
    expect(
      screen.getByText("Only moves that will succeed are shown"),
    ).toBeInTheDocument();
    expect(items.map((i) => i.textContent)).toEqual([
      "In progress",
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
      await screen.findByRole("menuitem", { name: "In progress" }),
    );

    expect(api.find("PATCH", ISSUE_URL)).toHaveLength(0);
    expect(
      screen.getByText("In progress needs an owner. Assign it to yourself?"),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "Assign to me and move to In progress",
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
    // ...but the person still sees the note, pre-filled, before resolving,
    // and the menu says so.
    const resolved = await screen.findByRole("menuitem", { name: /^Resolved/ });
    expect(resolved).toHaveTextContent(
      "Resolved · asks for a note, pre-filled from the confirmed cause",
    );
    await user.click(resolved);
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

    // Labels show as pills with "＋", which opens the box to add one.
    expect(screen.queryByRole("textbox", { name: "Add label" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "New label" }));
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

  it("has no timeline: the thread records when things happened", async () => {
    stubSidebar({ body: baseIssue });
    renderSidebar("member");

    expect(await screen.findByText("Raj Patel")).toBeInTheDocument();
    expect(screen.queryByText("Timeline")).not.toBeInTheDocument();
  });
});

function run(overrides: Record<string, unknown>) {
  return {
    id: "run-1",
    issue_id: "issue-1",
    investigation_id: "inv-1",
    trigger_type: "human",
    brief: { symptom: "Completed orders dropped" },
    source_thread_id: "thread-1",
    parent_run_id: null,
    execution_profile: "standard",
    approval_status: null,
    confidence: null,
    root_cause_tag: null,
    synthesis_summary: null,
    created_at: "2026-09-14T08:20:00Z",
    completed_at: null,
    outcome_verdict: null,
    outcome_note: null,
    outcome_reviewed_by: null,
    outcome_reviewed_at: null,
    number: 1,
    status: "running",
    error: null,
    ...overrides,
  };
}

describe("IssueSidebar investigations", () => {
  it("lists each run by number and depth with how it ended", async () => {
    stubApi({
      "GET /api/v1/users/": { body: { users: [], total: 0 } },
      [`GET ${ISSUE_URL}/watchers`]: { body: { items: [], total: 0 } },
      [`GET ${ISSUE_URL}/investigation-runs`]: {
        body: {
          items: [
            run({
              id: "run-3",
              investigation_id: "inv-3",
              number: 3,
              execution_profile: "safe",
            }),
            run({
              id: "run-1",
              investigation_id: "inv-1",
              number: 1,
              status: "completed",
              completed_at: "2026-09-14T08:44:00Z",
              confidence: 0.91,
            }),
            run({
              id: "run-2",
              investigation_id: "inv-2",
              number: 2,
              execution_profile: "deep",
              status: "failed",
              completed_at: "2026-09-14T09:01:00Z",
              error: "Anthropic rejected the API key (401).",
            }),
            run({
              id: "run-4",
              investigation_id: "inv-4",
              number: 4,
              status: "completed",
              confidence: 0.8,
              outcome_verdict: "confirmed",
            }),
            run({
              id: "run-5",
              investigation_id: "inv-5",
              number: 5,
              status: "completed",
              outcome_verdict: "rejected",
            }),
          ],
          total: 5,
        },
      },
    });
    renderSidebar("member");

    const list = await screen.findByRole("list", { name: "Investigations" });
    const rows = within(list).getAllByRole("link");
    expect(rows.map((r) => r.textContent)).toEqual([
      "#1 · standarddone · 0.91",
      "#2 · deepfailed",
      "#3 · saferunning",
      "#4 · standardconfirmed",
      "#5 · standardrejected",
    ]);
    expect(rows[1]).toHaveAttribute("href", "/investigations/inv-2");
    // A failed run is red, not "running" forever.
    expect(within(rows[1]).getByText("failed").className).toContain("red");
    expect(within(rows[2]).getByText("running").className).toContain("violet");
  });

  it("numbers runs listed without a number by start time", async () => {
    const legacy = (id: string, created_at: string) =>
      run({ id, investigation_id: `inv-${id}`, created_at, number: undefined });
    stubApi({
      "GET /api/v1/users/": { body: { users: [], total: 0 } },
      [`GET ${ISSUE_URL}/watchers`]: { body: { items: [], total: 0 } },
      [`GET ${ISSUE_URL}/investigation-runs`]: {
        body: {
          items: [
            legacy("b", "2026-09-14T09:00:00Z"),
            legacy("a", "2026-09-14T08:00:00Z"),
          ],
          total: 2,
        },
      },
    });
    renderSidebar("member");

    const list = await screen.findByRole("list", { name: "Investigations" });
    expect(
      within(list)
        .getAllByRole("link")
        .map((r) => r.getAttribute("href")),
    ).toEqual(["/investigations/inv-a", "/investigations/inv-b"]);
  });
});

describe("IssueSidebar dataset", () => {
  const DATASOURCES = {
    body: {
      items: [
        {
          id: "src-1",
          name: "warehouse",
          type: "postgres",
          category: "database",
          is_active: true,
          is_default: true,
          status: "connected",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total: 1,
    },
  };

  function dataset(native_path: string) {
    return {
      id: "dset-9",
      datasource_id: "src-1",
      native_path,
      name: "orders",
      table_type: "table",
      created_at: "2026-01-01T00:00:00Z",
    };
  }

  it("links to the dataset's page when a datasource has synced it", async () => {
    const api = stubApi({
      "GET /api/v1/users/": { body: { users: [], total: 0 } },
      "GET /api/v1/datasources": DATASOURCES,
      "GET /api/v1/datasources/src-1/datasets": {
        body: {
          datasets: [
            dataset("analytics.public.orders_archive"),
            dataset("analytics.public.orders"),
          ],
          total: 2,
        },
      },
    });
    renderSidebar("member");

    const link = await screen.findByRole("link", {
      name: "open dataset page →",
    });
    expect(link).toHaveAttribute("href", "/datasets/dset-9");
    expect(
      api
        .find("GET", "/api/v1/datasources/src-1/datasets")[0]
        .query.get("search"),
    ).toBe("analytics.public.orders");
  });

  it("shows the dataset without a link when no datasource has it", async () => {
    const api = stubApi({
      "GET /api/v1/users/": { body: { users: [], total: 0 } },
      "GET /api/v1/datasources": DATASOURCES,
      "GET /api/v1/datasources/src-1/datasets": {
        body: { datasets: [dataset("analytics.public.orders_v2")], total: 1 },
      },
    });
    renderSidebar("member");

    expect(
      await screen.findByText("analytics.public.orders"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        api.find("GET", "/api/v1/datasources/src-1/datasets"),
      ).toHaveLength(1),
    );
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(
      screen.queryByRole("link", { name: "open dataset page →" }),
    ).not.toBeInTheDocument();
  });
});
