import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import type { ThreadMessage, ToolCall } from "@/lib/api/issue-threads";
import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubApi } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueThread } from "./IssueThread";
import { toolCallsSummary } from "./ToolCalls";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const ISSUE = "issue-1";
const THREAD = "thread-1";
const THREADS = `/api/v1/issues/${ISSUE}/threads`;
const MESSAGES = `${THREADS}/${THREAD}/messages`;

function message(overrides: Partial<ThreadMessage>): ThreadMessage {
  return {
    id: "m-1",
    thread_id: THREAD,
    seq: 1,
    rev: 1,
    author_kind: "user",
    author_user_id: "user-1",
    requested_by_user_id: null,
    request_message_id: null,
    kind: "comment",
    body_md: "",
    payload: {},
    status: "complete",
    asks_agent: false,
    reply_to_id: null,
    created_at: "2026-09-14T08:10:00Z",
    updated_at: "2026-09-14T08:10:00Z",
    edited_at: null,
    deleted_at: null,
    ...overrides,
  };
}

const question = message({
  id: "q-1",
  seq: 1,
  rev: 1,
  body_md: "is it every region?",
  asks_agent: true,
});

const queuedReply = message({
  id: "a-1",
  seq: 2,
  rev: 2,
  author_kind: "agent",
  author_user_id: null,
  requested_by_user_id: "user-1",
  request_message_id: "q-1",
  reply_to_id: "q-1",
  kind: "agent_reply",
  status: "queued",
});

function stubThread(messages: ThreadMessage[], extra = {}) {
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
    [`GET ${THREADS}`]: {
      body: {
        items: [
          {
            id: THREAD,
            issue_id: ISSUE,
            kind: "shared",
            owner_user_id: null,
            title: null,
            created_at: "2026-09-14T08:00:00Z",
          },
        ],
      },
    },
    [`GET ${MESSAGES}`]: { body: { items: messages } },
    ...extra,
  });
}

function renderThread(role: OrgRole = "member") {
  return renderAsRole(<IssueThread issueId={ISSUE} />, role);
}

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("IssueThread composer", () => {
  it("switches between commenting and asking the agent", async () => {
    const api = stubThread([], {
      [`POST ${MESSAGES}`]: (req: { body: unknown }) => ({
        status: 201,
        body: message({
          id: "q-9",
          seq: 1,
          body_md: (req.body as { body_md: string }).body_md,
          asks_agent: true,
        }),
      }),
    });
    const user = userEvent.setup();
    renderThread("member");

    const comment = await screen.findByRole("button", { name: "Comment" });
    const ask = screen.getByRole("button", { name: "Ask agent" });
    expect(comment).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText("Comments are visible to everyone on this issue."),
    ).toBeInTheDocument();

    await user.click(ask);
    expect(ask).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText("Agent replies are visible to everyone on this issue."),
    ).toBeInTheDocument();

    const box = screen.getByPlaceholderText(
      "Ask the agent. It runs read-only queries as you.",
    );
    await user.click(box);
    await user.paste("is it every region?");
    await user.keyboard("{Control>}{Enter}{/Control}");

    await waitFor(() => expect(api.find("POST", MESSAGES)).toHaveLength(1));
    expect(api.find("POST", MESSAGES)[0].body).toEqual({
      body_md: "is it every region?",
      ask_agent: true,
    });
    expect(await screen.findByText("is it every region?")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("lets viewers comment but not ask the agent, and says why", async () => {
    const api = stubThread([], {
      [`POST ${MESSAGES}`]: {
        status: 201,
        body: message({ body_md: "FYI" }),
      },
    });
    const user = userEvent.setup();
    renderThread("viewer");

    const ask = await screen.findByRole("button", { name: "Ask agent" });
    expect(ask).toBeDisabled();
    expect(
      screen.getByText(/Viewers can comment but can't ask the agent/),
    ).toBeInTheDocument();

    await user.click(screen.getByLabelText("Comment"));
    await user.paste("FYI");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(api.find("POST", MESSAGES)).toHaveLength(1));
    expect(api.find("POST", MESSAGES)[0].body).toEqual({
      body_md: "FYI",
      ask_agent: false,
    });
  });

  it("shows the server's reason when asking fails", async () => {
    stubThread([], {
      [`POST ${MESSAGES}`]: {
        status: 429,
        body: { detail: "You already have three agent answers in progress" },
      },
    });
    const user = userEvent.setup();
    renderThread("member");

    await user.click(await screen.findByRole("button", { name: "Ask agent" }));
    await user.click(screen.getByLabelText("Question"));
    await user.paste("why?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Couldn't ask the agent", {
        description: "You already have three agent answers in progress",
      }),
    );
    expect(screen.getByLabelText("Question")).toHaveValue("why?");
  });
});

describe("IssueThread streaming", () => {
  it("renders an agent answer as it streams in", async () => {
    stubThread([question, queuedReply]);
    renderThread("member");

    expect(
      await screen.findByText("Waiting for the agent…"),
    ).toBeInTheDocument();
    expect(screen.getByText("is it every region?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const stream = FakeEventSource.latest();
    expect(stream.url).toContain(`${THREADS}/${THREAD}/stream?`);
    expect(stream.url).toContain("after=2");
    expect(stream.url).toContain("token=");

    act(() => {
      stream.open();
      stream.emit(
        "message",
        { ...queuedReply, rev: 3, status: "streaming", body_md: "Yes. Every" },
        "3",
      );
    });
    expect(await screen.findByText("Yes. Every")).toBeInTheDocument();
    expect(screen.getByText("Answering…")).toBeInTheDocument();

    act(() => {
      stream.emit(
        "message",
        {
          ...queuedReply,
          rev: 4,
          status: "complete",
          body_md: "Yes. Every region dropped by 28–32%.",
        },
        "4",
      );
      // A late duplicate of an older rev never rolls the answer back.
      stream.emit(
        "message",
        { ...queuedReply, rev: 3, status: "streaming", body_md: "Yes. Every" },
        "3",
      );
    });
    expect(
      await screen.findByText("Yes. Every region dropped by 28–32%."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Answering…")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
  });

  it("reconnects after an error from the last rev it saw", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      stubThread([question, queuedReply]);
      renderThread("member");
      await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
      const first = FakeEventSource.latest();

      act(() => {
        first.emit("message", { ...queuedReply, rev: 7, status: "streaming" });
        first.fail();
      });
      expect(first.closed).toBe(true);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_500);
      });
      expect(FakeEventSource.instances).toHaveLength(2);
      expect(FakeEventSource.latest().url).toContain("after=7");
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels the caller's own running answer", async () => {
    const api = stubThread([question, queuedReply], {
      [`POST ${MESSAGES}/a-1/cancel`]: {
        body: { ...queuedReply, rev: 3, status: "cancelled" },
      },
    });
    const user = userEvent.setup();
    renderThread("member");

    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(await screen.findByText("Cancelled.")).toBeInTheDocument();
    expect(api.find("POST", `${MESSAGES}/a-1/cancel`)).toHaveLength(1);
  });

  it("does not offer Cancel on someone else's answer", async () => {
    stubThread([
      { ...question, author_user_id: "user-2" },
      { ...queuedReply, requested_by_user_id: "user-2" },
    ]);
    renderThread("member");

    expect(
      await screen.findByText(/replying to Raj Patel/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
  });
});

describe("IssueThread tool calls", () => {
  it("expands a query to its SQL and result table", async () => {
    const sql =
      "SELECT region, count(*) AS completed FROM orders GROUP BY region";
    const reply = message({
      ...queuedReply,
      status: "complete",
      body_md: "Every region dropped.",
      payload: {
        tool_calls: [
          {
            id: "call-1",
            tool: "run_query",
            input: { sql, purpose: "Split completed orders by region" },
            status: "ok",
            summary: "2 rows",
            query_result_id: "qr-1",
            error_code: null,
            duration_ms: 212,
            row_count: 2,
          },
        ],
      },
    });
    const api = stubThread([question, reply], {
      [`GET ${THREADS}/${THREAD}/query-results/qr-1`]: {
        body: {
          id: "qr-1",
          message_id: "a-1",
          tool_call_id: "call-1",
          sql,
          dialect: "postgres",
          columns: [{ name: "region" }, { name: "completed" }],
          rows: [
            { region: "us", completed: 18402 },
            { region: "eu", completed: 12115 },
          ],
          row_count: 2,
          truncated: false,
          duration_ms: 212,
          error: null,
          created_at: "2026-09-14T08:10:00Z",
        },
      },
    });
    const user = userEvent.setup();
    renderThread("member");

    const toggle = await screen.findByRole("button", {
      name: "Ran 1 query · 212 ms · 2 rows",
    });
    expect(toggle).toHaveTextContent("▸ Ran 1 query · 212 ms · 2 rows");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      api.find("GET", `${THREADS}/${THREAD}/query-results/qr-1`),
    ).toHaveLength(0);

    await user.click(toggle);

    expect(await screen.findByText(sql)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("region")).toBeInTheDocument();
    expect(within(table).getByText("18402")).toBeInTheDocument();
    expect(within(table).getByText("eu")).toBeInTheDocument();
    expect(toggle).toHaveTextContent("▾ Ran 1 query");
    expect(
      screen.getByText(
        /2 rows · 212 ms · postgres · Snapshot saved with this message/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Copy SQL" }),
    ).toBeInTheDocument();
  });
});

describe("toolCallsSummary", () => {
  function call(overrides: Partial<ToolCall>): ToolCall {
    return {
      id: "call-1",
      tool: "run_query",
      input: {},
      status: "ok",
      summary: "",
      query_result_id: "qr-1",
      error_code: null,
      ...overrides,
    };
  }

  it("totals the time and rows the queries took", () => {
    expect(toolCallsSummary([call({ duration_ms: 212, row_count: 4 })])).toBe(
      "Ran 1 query · 212 ms · 4 rows",
    );
    expect(
      toolCallsSummary([
        call({ duration_ms: 200, row_count: 17 }),
        call({ id: "call-2", duration_ms: 280, row_count: 4 }),
      ]),
    ).toBe("Ran 2 queries · 480 ms · 21 rows");
    expect(
      toolCallsSummary([
        call({ duration_ms: 1500, row_count: 18400 }),
        call({ id: "call-2", tool: "describe_table" }),
      ]),
    ).toBe("Ran 1 query · 1,500 ms · 18,400 rows · 1 other tool call");
  });

  it("falls back to the count on messages recorded without totals", () => {
    expect(
      toolCallsSummary([call({}), call({ id: "call-2", tool: "list_tables" })]),
    ).toBe("Ran 1 query · 1 other tool call");
    expect(toolCallsSummary([call({ tool: "describe_table" })])).toBe(
      "Used 1 tool",
    );
  });

  it("counts no rows for a query that failed", () => {
    expect(
      toolCallsSummary([
        call({ duration_ms: 30, row_count: 3 }),
        call({
          id: "call-2",
          status: "error",
          query_result_id: null,
          duration_ms: 5,
          row_count: null,
        }),
      ]),
    ).toBe("Ran 2 queries · 35 ms · 3 rows");
  });
});

describe("IssueThread opening entry", () => {
  const ISSUE_URL = `/api/v1/issues/${ISSUE}`;

  function issue(overrides: Record<string, unknown> = {}) {
    return {
      id: ISSUE,
      number: 42,
      title: "Completed orders dropped",
      description: "Completed orders fell **30%** on the 14th.",
      status: "open",
      priority: null,
      severity: null,
      dataset_id: null,
      due_at: null,
      assignee_user_id: null,
      acknowledged_by: null,
      created_by_user_id: "user-1",
      author_type: "human",
      source_provider: null,
      source_external_id: null,
      source_external_url: null,
      resolution_note: null,
      context: {},
      labels: [],
      allowed_transitions: [],
      transition_requirements: {},
      created_at: "2026-09-14T08:02:00Z",
      updated_at: "2026-09-14T08:02:00Z",
      closed_at: null,
      ...overrides,
    };
  }

  function opened(overrides: Partial<ThreadMessage> = {}) {
    return message({
      id: "e-1",
      seq: 1,
      rev: 1,
      author_kind: "system",
      author_user_id: "user-1",
      kind: "event",
      body_md: "Issue created",
      payload: { event_type: "created", title: "Completed orders dropped" },
      created_at: "2026-09-14T08:02:00Z",
      ...overrides,
    });
  }

  it("opens with who opened the issue and its description, which they can edit", async () => {
    const api = stubThread([opened()], {
      [`GET ${ISSUE_URL}`]: { body: issue() },
      [`PATCH ${ISSUE_URL}`]: (req: { body: unknown }) => ({
        body: issue(req.body as Record<string, unknown>),
      }),
    });
    const user = userEvent.setup();
    renderThread("member");

    expect(await screen.findByText(/opened the issue/)).toHaveTextContent(
      /^Ada · opened the issue · /,
    );
    expect((await screen.findByText("30%")).tagName).toBe("STRONG");
    expect(screen.queryByText("Issue created")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editor = screen.getByLabelText("Edit description");
    await user.clear(editor);
    await user.paste("Completed orders fell 30%; only app_v2.");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Completed orders fell 30%; only app_v2."),
    ).toBeInTheDocument();
    expect(api.find("PATCH", ISSUE_URL)[0].body).toEqual({
      description: "Completed orders fell 30%; only app_v2.",
    });
  });

  it("says when there's no description, and only its author can edit", async () => {
    stubThread([opened({ author_user_id: "user-2" })], {
      [`GET ${ISSUE_URL}`]: {
        body: issue({ description: null, created_by_user_id: "user-2" }),
      },
    });
    renderThread("member");

    expect(await screen.findByText("No description.")).toBeInTheDocument();
    expect(screen.getByText(/opened the issue/)).toHaveTextContent(
      /^Raj Patel · opened the issue/,
    );
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("starts an issue dataing opened with the event line", async () => {
    stubThread(
      [
        opened({
          author_user_id: null,
          payload: { event_type: "created", source_provider: "monte_carlo" },
        }),
      ],
      {
        [`GET ${ISSUE_URL}`]: {
          body: issue({
            created_by_user_id: null,
            source_provider: "monte_carlo",
          }),
        },
      },
    );
    renderThread("member");

    expect(
      await screen.findByText(/Issue opened by dataing from monte_carlo ·/),
    ).toHaveTextContent(/^⚑ Issue opened by dataing from monte_carlo · /);
    expect((await screen.findByText("30%")).tagName).toBe("STRONG");
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("still shows the description on a thread without an opening entry", async () => {
    stubThread([], {
      [`GET ${ISSUE_URL}`]: { body: issue({ created_by_user_id: "user-2" }) },
    });
    renderThread("member");

    expect((await screen.findByText("30%")).tagName).toBe("STRONG");
    expect(screen.getByText(/opened the issue/)).toHaveTextContent(
      /^Raj Patel · opened the issue/,
    );
  });
});

describe("IssueThread comments", () => {
  it("shows author names and lets the author edit their comment", async () => {
    const own = message({ id: "c-1", seq: 1, body_md: "first take" });
    const other = message({
      id: "c-2",
      seq: 2,
      author_user_id: "user-2",
      body_md: "my dashboard counts **completed** only",
    });
    const api = stubThread([own, other], {
      [`PATCH ${MESSAGES}/c-1`]: (req: { body: unknown }) => ({
        body: {
          ...own,
          rev: 5,
          body_md: (req.body as { body_md: string }).body_md,
          edited_at: "2026-09-14T08:20:00Z",
        },
      }),
    });
    const user = userEvent.setup();
    renderThread("member");

    expect(await screen.findByText("Raj Patel")).toBeInTheDocument();
    expect(screen.getByText("completed").tagName).toBe("STRONG");
    // Only the author's own comment offers Edit.
    expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editor = screen.getByLabelText("Edit comment");
    await user.clear(editor);
    await user.paste("second take");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("second take")).toBeInTheDocument();
    expect(api.find("PATCH", `${MESSAGES}/c-1`)[0].body).toEqual({
      body_md: "second take",
    });
  });
});
