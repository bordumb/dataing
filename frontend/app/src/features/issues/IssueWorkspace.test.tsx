import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubApi, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { message } from "./hub/test-helpers";
import { IssueWorkspace } from "./IssueWorkspace";

const ISSUE_URL = "/api/v1/issues/issue-1";

const ISSUE = {
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
};

const USERS = {
  users: [
    {
      id: "user-2",
      email: "raj@acme.test",
      name: "Raj Patel",
      role: "member",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 1,
};

function thread(id: string, kind: "shared" | "scratch", title?: string) {
  return {
    id,
    issue_id: "issue-1",
    kind,
    owner_user_id: kind === "scratch" ? "user-1" : null,
    title: title ?? null,
    created_at: "2026-09-01T00:00:00Z",
  };
}

function stubWorkspace({
  issue = {},
  messages = [],
  scratch = [],
  watchers = [],
}: {
  issue?: Record<string, unknown>;
  messages?: unknown[];
  scratch?: unknown[];
  watchers?: unknown[];
} = {}) {
  const empty = { body: { items: [], total: 0 } };
  return stubApi({
    [`GET ${ISSUE_URL}`]: { body: { ...ISSUE, ...issue } },
    "GET /api/v1/users/": { body: USERS },
    [`GET ${ISSUE_URL}/watchers`]: {
      body: { items: watchers, total: watchers.length },
    },
    [`GET ${ISSUE_URL}/investigation-runs`]: empty,
    [`GET ${ISSUE_URL}/threads`]: {
      body: { items: [thread("thread-1", "shared"), ...scratch] },
    },
    [`GET ${ISSUE_URL}/threads/thread-1/messages`]: {
      body: { items: messages },
    },
    "GET /api/v1/datasources": empty,
  });
}

function renderWorkspace(role: OrgRole) {
  return renderAsRole(
    <Routes>
      <Route path="/issues/:id" element={<IssueWorkspace />} />
    </Routes>,
    role,
    "/issues/issue-1",
  );
}

beforeAll(() => stubRadixDom());

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("IssueWorkspace", () => {
  it("keeps viewers to watching and commenting", async () => {
    stubWorkspace();
    renderWorkspace("viewer");

    expect(
      await screen.findByRole("heading", {
        name: "Null spike in orders.email",
      }),
    ).toBeInTheDocument();
    // The description is the thread's first entry, not a card of its own.
    expect((await screen.findByText("jumped")).tagName).toBe("STRONG");
    expect(screen.queryByText("Description")).not.toBeInTheDocument();
    expect(await screen.findByText("Watch")).toBeInTheDocument();
    expect(
      await screen.findByPlaceholderText(
        "Write a comment for the team (Markdown)",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Investigate…/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Change status/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /My scratch chats/ }),
    ).not.toBeInTheDocument();
  });

  it("lets members run investigations and change status", async () => {
    stubWorkspace();
    renderWorkspace("member");

    // The composer hands the thread to an investigation.
    expect(
      await screen.findAllByRole("button", { name: /Investigate…/ }),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: /Change status/ }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Ask agent" }),
    ).toBeEnabled();
  });

  it("puts the issue's number, title, status, priority and dataset in one bar", async () => {
    stubWorkspace({
      issue: {
        status: "in_progress",
        priority: "P1",
        dataset_id: "analytics.public.orders",
      },
    });
    renderWorkspace("member");

    const title = await screen.findByRole("heading", {
      level: 1,
      name: "Null spike in orders.email",
    });
    const bar = title.parentElement!;
    expect(bar).toHaveTextContent(
      "#7Null spike in orders.emailIn ProgressP1dataset analytics.public.orders",
    );
    expect(
      within(bar).getByRole("link", { name: "Back to issues" }),
    ).toHaveAttribute("href", "/issues");
  });

  it("heads the thread with its tabs and who is watching", async () => {
    stubWorkspace({
      scratch: [
        thread("scratch-1", "scratch", "Backfill sizing"),
        thread("scratch-2", "scratch", "v2 enum check"),
      ],
      watchers: [
        { user_id: "user-1", created_at: "2026-09-01T00:00:00Z" },
        { user_id: "user-2", created_at: "2026-09-01T00:00:00Z" },
      ],
      messages: [
        message({
          id: "e-1",
          author_kind: "system",
          author_user_id: "user-2",
          kind: "event",
          body_md: "Created",
          payload: { event_type: "created" },
        }),
      ],
    });
    const user = userEvent.setup();
    renderWorkspace("member");

    const tabs = await screen.findByRole("group", { name: "Threads" });
    expect(
      within(tabs).getByRole("button", { name: "Shared thread" }),
    ).toHaveAttribute("aria-current", "true");
    const scratchTab = await within(tabs).findByRole("button", {
      name: "My scratch chats (2)",
    });
    expect(await screen.findByText("2 watching")).toBeInTheDocument();
    act(() => FakeEventSource.latest().open());
    expect(await screen.findByText("2 watching · live")).toBeInTheDocument();

    // The first entry says who opened the issue, with its description.
    expect(
      await screen.findByText(/opened the issue/, { exact: false }),
    ).toHaveTextContent("Raj Patel · opened the issue");
    expect(screen.getByText("jumped").tagName).toBe("STRONG");

    await user.click(scratchTab);
    expect(
      await screen.findByRole("dialog", { name: "My scratch chats" }),
    ).toBeInTheDocument();
  });

  it("keeps the sidebar to one panel in the mockup's order", async () => {
    stubWorkspace({ issue: { dataset_id: "analytics.public.orders" } });
    renderWorkspace("member");

    const sidebar = await screen.findByRole("complementary", {
      name: "Issue details",
    });
    expect(
      await within(sidebar).findByText("Your scratch chats"),
    ).toBeInTheDocument();
    expect(
      within(sidebar)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual([
      "Status",
      "Details",
      "Dataset",
      "Investigations",
      "Watchers",
      "Your scratch chats",
    ]);
    expect(screen.queryByText("Timeline")).not.toBeInTheDocument();
    expect(
      within(sidebar).getByRole("button", { name: "New scratch chat" }),
    ).toHaveTextContent("＋New scratch chat");
  });
});
