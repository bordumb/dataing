import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueHubProvider } from "../hub/IssueHub";
import {
  ISSUE,
  MESSAGES,
  RUNS,
  SHARED_THREAD,
  THREAD,
  THREADS,
  message,
  stubHub,
} from "../hub/test-helpers";
import { IssueThread } from "../thread/IssueThread";
import { ScratchChatsSection } from "./ScratchChatsSection";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const SCRATCH = "scratch-1";
const SCRATCH_URL = `${THREADS}/${SCRATCH}`;
const SCRATCH_MESSAGES = `${SCRATCH_URL}/messages`;

const scratchThread = {
  id: SCRATCH,
  issue_id: ISSUE,
  kind: "scratch",
  owner_user_id: "user-1",
  title: "v2 enum check",
  created_at: "2026-09-14T08:33:00Z",
};

const question = message({
  id: "sq-1",
  thread_id: SCRATCH,
  seq: 1,
  rev: 1,
  asks_agent: true,
  body_md: "What status values does app_v2 write since the 13th?",
});

const answer = message({
  id: "sa-1",
  thread_id: SCRATCH,
  seq: 2,
  rev: 2,
  kind: "agent_reply",
  author_kind: "agent",
  author_user_id: null,
  requested_by_user_id: "user-1",
  body_md: "Since 09-14 09:02 UTC, app_v2 writes COMPLETE.",
});

const streaming = message({
  id: "sa-2",
  thread_id: SCRATCH,
  seq: 4,
  rev: 4,
  kind: "agent_reply",
  author_kind: "agent",
  author_user_id: null,
  requested_by_user_id: "user-1",
  status: "streaming",
  body_md: "Looking at",
});

function stubScratch(
  chats: object[] = [scratchThread],
  scratchMessages = [question, answer],
  extra = {},
) {
  return stubHub([], {
    [`GET ${THREADS}`]: { body: { items: [SHARED_THREAD, ...chats] } },
    [`GET ${SCRATCH_MESSAGES}`]: { body: { items: scratchMessages } },
    ...extra,
  });
}

function renderPage(role: OrgRole = "member") {
  return renderAsRole(
    <IssueHubProvider
      issueId={ISSUE}
      issueTitle="Completed orders dropped"
      datasetId="analytics.public.orders"
    >
      <IssueThread issueId={ISSUE} />
      <ScratchChatsSection issueId={ISSUE} />
    </IssueHubProvider>,
    role,
  );
}

beforeAll(() => stubRadixDom());

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Scratch drawer", () => {
  it("creates a scratch chat and asks the agent privately", async () => {
    const api = stubScratch([], [], {
      [`POST ${THREADS}`]: (req: { body: unknown }) => ({
        status: 201,
        body: {
          ...scratchThread,
          title: (req.body as { title: string | null }).title,
        },
      }),
      [`POST ${SCRATCH_MESSAGES}`]: (req: { body: unknown }) => ({
        status: 201,
        body: message({
          id: "sq-9",
          thread_id: SCRATCH,
          asks_agent: true,
          body_md: (req.body as { body_md: string }).body_md,
        }),
      }),
    });
    const user = userEvent.setup();
    renderPage("member");

    await user.click(
      await screen.findByRole("button", { name: /My scratch chats/ }),
    );
    const drawer = await screen.findByRole("dialog");
    expect(
      within(drawer).getByText(/No scratch chats yet/),
    ).toBeInTheDocument();

    await user.click(within(drawer).getByLabelText("New chat title"));
    await user.paste("v2 enum check");
    await user.click(within(drawer).getByRole("button", { name: "New chat" }));

    await waitFor(() => expect(api.find("POST", THREADS)).toHaveLength(1));
    expect(api.find("POST", THREADS)[0].body).toEqual({
      title: "v2 enum check",
    });
    expect(
      await within(drawer).findByText("Scratch: v2 enum check"),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("private")).toBeInTheDocument();

    // Scratch chats ask the agent by default, and say who can see them.
    const box = within(drawer).getByPlaceholderText("Ask the agent privately…");
    expect(
      within(drawer).getAllByText(
        "Only you can see this chat. Queries still run as you and are audited.",
      ).length,
    ).toBeGreaterThan(0);
    await user.click(box);
    await user.paste("What status values does app_v2 write?");
    await user.click(within(drawer).getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(api.find("POST", SCRATCH_MESSAGES)).toHaveLength(1),
    );
    expect(api.find("POST", SCRATCH_MESSAGES)[0].body).toEqual({
      body_md: "What status values does app_v2 write?",
      ask_agent: true,
    });
    // Nothing was posted to the shared thread.
    expect(api.find("POST", MESSAGES)).toHaveLength(0);
  });

  it("publishes selected messages to the shared thread", async () => {
    const api = stubScratch([scratchThread], [question, answer, streaming], {
      [`POST ${SCRATCH_URL}/publish`]: {
        status: 201,
        body: message({
          id: "pub-1",
          thread_id: THREAD,
          seq: 7,
          rev: 7,
          kind: "published",
          body_md: "For the backfill\n\n**Agent:** app_v2 writes COMPLETE.",
        }),
      },
    });
    const user = userEvent.setup();
    renderPage("member");

    // The sidebar lists the person's scratch chats.
    const list = await screen.findByRole("list", {
      name: "Your scratch chats",
    });
    await user.click(
      within(list).getByRole("button", { name: "v2 enum check" }),
    );

    const drawer = await screen.findByRole("dialog");
    await within(drawer).findByText(
      "Since 09-14 09:02 UTC, app_v2 writes COMPLETE.",
    );
    const publish = within(drawer).getByRole("button", {
      name: "Publish selected (0)",
    });
    expect(publish).toBeDisabled();
    // An answer still streaming can't be selected.
    expect(
      within(drawer).queryByLabelText("Select message 4"),
    ).not.toBeInTheDocument();

    await user.click(within(drawer).getByLabelText("Select message 2"));
    await user.click(within(drawer).getByLabelText("Select message 1"));
    await user.click(
      within(drawer).getByRole("button", { name: "Publish selected (2)" }),
    );
    await user.click(within(drawer).getByLabelText("Note for the team"));
    await user.paste("For the backfill");
    await user.click(within(drawer).getByRole("button", { name: "Publish" }));

    await waitFor(() =>
      expect(api.find("POST", `${SCRATCH_URL}/publish`)).toHaveLength(1),
    );
    expect(api.find("POST", `${SCRATCH_URL}/publish`)[0].body).toEqual({
      message_ids: ["sq-1", "sa-1"],
      note: "For the backfill",
    });
    expect(toast.success).toHaveBeenCalledWith(
      "Published to the shared thread",
    );
    expect(
      within(drawer).getByRole("button", { name: "Publish selected (0)" }),
    ).toBeDisabled();

    // The published message shows in the shared thread.
    expect(
      await screen.findByText("shared from a scratch chat", { exact: false }),
    ).toBeInTheDocument();
  });

  it("investigates from a scratch chat", async () => {
    const draft = message({
      id: "sb-1",
      thread_id: SCRATCH,
      seq: 3,
      rev: 3,
      kind: "brief",
      author_kind: "agent",
      author_user_id: null,
      requested_by_user_id: "user-1",
      status: "complete",
      body_md: "**Investigation brief**",
      payload: {
        brief: {
          version: 1,
          symptom: "app_v2 completed orders vanished",
          scope: { datasource_id: null, tables: [], time_window: null },
          findings: [
            {
              statement: "app_v2 writes COMPLETE since 09-14",
              message_id: "sa-1",
              query_result_id: null,
            },
          ],
          ruled_out: [],
          leads: [],
          notes: "",
        },
      },
    });
    const api = stubScratch([scratchThread], [question, answer], {
      [`POST ${SCRATCH_URL}/brief-drafts`]: { status: 201, body: draft },
      [`POST ${RUNS}`]: { status: 201, body: {} },
    });
    const user = userEvent.setup();
    renderPage("member");

    const list = await screen.findByRole("list", {
      name: "Your scratch chats",
    });
    await user.click(
      within(list).getByRole("button", { name: "v2 enum check" }),
    );
    const drawer = await screen.findByRole("dialog");
    await user.click(
      await within(drawer).findByRole("button", {
        name: "Investigate from here",
      }),
    );

    await waitFor(() =>
      expect(api.find("POST", `${SCRATCH_URL}/brief-drafts`)).toHaveLength(1),
    );
    const editor = await screen.findByRole("dialog", {
      name: "Hand off to an investigation",
    });
    expect(within(editor).getByLabelText("Symptom")).toHaveValue(
      "app_v2 completed orders vanished",
    );
    expect(
      within(editor).getByRole("button", {
        name: /from the agent's answer to Ada in your scratch chat/,
      }),
    ).toBeInTheDocument();
    await user.click(
      within(editor).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() => expect(api.find("POST", RUNS)).toHaveLength(1));
    expect(
      (api.find("POST", RUNS)[0].body as { source_thread_id: string })
        .source_thread_id,
    ).toBe(SCRATCH);
  });

  it("renames and deletes a scratch chat", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const api = stubScratch([scratchThread], [question], {
      [`PATCH ${SCRATCH_URL}`]: (req: { body: unknown }) => ({
        body: { ...scratchThread, ...(req.body as object) },
      }),
      [`DELETE ${SCRATCH_URL}`]: { status: 204 },
    });
    const user = userEvent.setup();
    renderPage("member");

    const list = await screen.findByRole("list", {
      name: "Your scratch chats",
    });
    await user.click(
      within(list).getByRole("button", { name: "v2 enum check" }),
    );
    const drawer = await screen.findByRole("dialog");

    await user.click(
      await within(drawer).findByRole("button", { name: "Rename chat" }),
    );
    const title = within(drawer).getByLabelText("Chat title");
    await user.clear(title);
    await user.paste("status enum");
    await user.click(within(drawer).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.find("PATCH", SCRATCH_URL)).toHaveLength(1));
    expect(api.find("PATCH", SCRATCH_URL)[0].body).toEqual({
      title: "status enum",
    });
    expect(
      await within(drawer).findByText("Scratch: status enum"),
    ).toBeInTheDocument();

    await user.click(
      within(drawer).getByRole("button", { name: "Delete chat" }),
    );
    await waitFor(() =>
      expect(api.find("DELETE", SCRATCH_URL)).toHaveLength(1),
    );
    expect(
      await within(drawer).findByText(/No scratch chats yet/),
    ).toBeInTheDocument();
  });

  it("isn't offered to viewers", async () => {
    stubScratch([]);
    renderPage("viewer");

    expect(
      await screen.findByPlaceholderText(
        "Write a comment for the team (Markdown)",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /My scratch chats/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Your scratch chats")).not.toBeInTheDocument();
  });
});
