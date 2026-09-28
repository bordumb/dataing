import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import type { ThreadMessage } from "@/lib/api/issue-threads";
import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubApi } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueThread } from "./IssueThread";

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

    const toggle = await screen.findByRole("button", { name: /Ran 1 query/ });
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
    expect(screen.getByText(/2 rows · 212 ms/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Copy SQL" }),
    ).toBeInTheDocument();
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
