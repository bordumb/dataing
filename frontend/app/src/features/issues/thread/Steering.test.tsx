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

import { FakeEventSource, stubRadixDom } from "@/test/api";

import {
  INV,
  INVESTIGATION,
  THREAD,
  message,
  renderHub,
  run,
  stubHub,
} from "../hub/test-helpers";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const STEERS = `${INVESTIGATION}/steers`;

const started = message({
  id: "i-1",
  seq: 3,
  rev: 3,
  kind: "investigation",
  payload: {
    investigation_id: INV,
    run_id: "run-1",
    execution_profile: "standard",
    brief: run().brief,
    source_thread_id: THREAD,
  },
});

const running = {
  investigation_id: INV,
  workflow_status: "running",
  current_step: "evaluate_hypotheses",
  progress: 0.5,
  is_complete: false,
  hypotheses: [
    {
      id: "h1",
      title: "app_v2 writes a different status",
      status: "supported",
    },
    { id: "h2", title: "events not landing", status: "running" },
    { id: "h3", title: "late-arriving events", status: "ruled_out" },
  ],
  pending_steers: [],
};

function steer(overrides: Record<string, unknown>) {
  return {
    id: "s-1",
    investigation_id: INV,
    issue_id: "issue-1",
    message_id: "m-steer",
    kind: "add_context",
    text: "",
    hypothesis_id: null,
    actor_user_id: "user-1",
    status: "pending",
    applied_phase: null,
    outcome: null,
    created_at: "2026-09-14T08:30:00Z",
    applied_at: null,
    ...overrides,
  };
}

const appliedRuleOut = steer({
  id: "s-ruled",
  kind: "rule_out",
  text: "events arrive within 5 min",
  hypothesis_id: "h3",
  actor_user_id: "user-2",
  status: "applied",
  applied_phase: "evaluation",
  outcome: "cancelled subagent h3",
});

function stubRunning(extra = {}) {
  return stubHub([started], {
    [`GET ${INVESTIGATION}/status`]: { body: running },
    [`GET ${STEERS}`]: { body: { items: [appliedRuleOut] } },
    [`POST ${STEERS}`]: (req: { body: unknown }) => ({
      status: 201,
      body: steer({ ...(req.body as object), id: "s-new" }),
    }),
    ...extra,
  });
}

beforeAll(() => stubRadixDom());

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Steer controls", () => {
  it("rules out a hypothesis that is still being tested", async () => {
    const api = stubRunning();
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    await within(card).findByText("running · evaluating");
    // Only the hypothesis still being tested offers Rule out.
    expect(
      within(card).getAllByRole("button", { name: /Rule out H/ }),
    ).toHaveLength(1);

    await user.click(within(card).getByRole("button", { name: "Rule out H2" }));
    const form = within(card).getByRole("form", {
      name: "Rule out H2 · events not landing",
    });
    await user.click(within(form).getByLabelText("Reason"));
    await user.paste("the loader logs show every batch");
    await user.click(within(form).getByRole("button", { name: "Rule out" }));

    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(1));
    expect(api.find("POST", STEERS)[0].body).toEqual({
      kind: "rule_out",
      text: "the loader logs show every batch",
      hypothesis_id: "h2",
    });
    expect(toast.success).toHaveBeenCalledWith("Steer sent", expect.anything());
  });

  it("adds context, adds a hypothesis and stops the run", async () => {
    const api = stubRunning();
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    await within(card).findByText("running · evaluating");

    await user.click(within(card).getByRole("button", { name: "Add context" }));
    const send = within(card).getByRole("button", { name: "Send context" });
    expect(send).toBeDisabled();
    await user.click(within(card).getByLabelText("Context"));
    await user.paste("app_v2 shipped 2026-09-14 09:00 UTC");
    await user.click(send);
    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(1));

    await user.click(
      await within(card).findByRole("button", { name: "Add hypothesis" }),
    );
    await user.click(within(card).getByLabelText("Hypothesis"));
    await user.paste("the dedup step drops v2 order ids");
    await user.click(
      within(card).getByRole("button", { name: "Send hypothesis" }),
    );
    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(2));

    await user.click(
      await within(card).findByRole("button", { name: "Stop and conclude" }),
    );
    const stop = within(card).getByRole("form", { name: "Stop and conclude" });
    await user.click(
      within(stop).getByRole("button", { name: "Stop and conclude" }),
    );
    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(3));

    expect(api.find("POST", STEERS).map((r) => r.body)).toEqual([
      { kind: "add_context", text: "app_v2 shipped 2026-09-14 09:00 UTC" },
      { kind: "add_hypothesis", text: "the dedup step drops v2 order ids" },
      { kind: "stop_and_synthesize", text: "" },
    ]);
  });

  it("lists steers with their status and who ruled out what", async () => {
    stubRunning({
      [`GET ${STEERS}`]: {
        body: {
          items: [
            appliedRuleOut,
            steer({
              id: "s-2",
              text: "v2 status enum changed",
              status: "pending",
            }),
          ],
        },
      },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    const steers = await within(card).findByRole("list", { name: "Steers" });
    const items = within(steers).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(
      'Steer by Raj Patel · rule out H3: "events arrive within 5 min" · applied cancelled subagent h3',
    );
    expect(items[1]).toHaveTextContent(
      'Steer by Ada · add context: "v2 status enum changed" · pending',
    );
    const h3 = within(card).getByLabelText("Hypothesis late-arriving events");
    expect(within(h3).getByText("ruled out by Raj Patel")).toBeInTheDocument();
    expect(within(h3).getByText("stopped")).toBeInTheDocument();
  });

  it("shows the run's steers to viewers without the controls", async () => {
    stubRunning();
    renderHub("viewer");

    const card = await screen.findByLabelText("Investigation");
    expect(
      await within(card).findByRole("list", { name: "Steers" }),
    ).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: /Rule out/ }),
    ).not.toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Add context" }),
    ).not.toBeInTheDocument();
  });

  it("offers no controls once the run has finished", async () => {
    stubRunning({
      [`GET ${INVESTIGATION}/status`]: {
        body: { investigation_id: INV, workflow_status: "completed" },
      },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    expect(await within(card).findByText("finished")).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Add context" }),
    ).not.toBeInTheDocument();
  });

  it("says so when the run doesn't take a steer", async () => {
    stubRunning({
      [`POST ${STEERS}`]: {
        status: 201,
        body: steer({
          status: "rejected",
          outcome:
            "The investigation isn't running: use Continue investigating",
        }),
      },
    });
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    await within(card).findByText("running · evaluating");
    await user.click(within(card).getByRole("button", { name: "Add context" }));
    await user.click(within(card).getByLabelText("Context"));
    await user.paste("x");
    await user.click(
      within(card).getByRole("button", { name: "Send context" }),
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "The investigation didn't take the steer",
        {
          description:
            "The investigation isn't running: use Continue investigating",
        },
      ),
    );
  });
});

describe("Proposed steers", () => {
  const reply = message({
    id: "a-1",
    seq: 5,
    rev: 5,
    kind: "agent_reply",
    author_kind: "agent",
    author_user_id: null,
    requested_by_user_id: "user-2",
    body_md: "I can't change the run myself. Here's a steer you can send:",
    payload: {
      proposals: [
        {
          run_id: INV,
          kind: "add_context",
          text: "Check whether app_v2 writes status values other than completed.",
          hypothesis_id: null,
        },
      ],
    },
  });

  function stubProposal(messages = [reply], extra = {}) {
    return stubHub(messages, {
      [`POST ${STEERS}`]: (req: { body: unknown }) => ({
        status: 201,
        body: steer({ ...(req.body as object), id: "s-new" }),
      }),
      ...extra,
    });
  }

  it("sends the proposal as a steer", async () => {
    const api = stubProposal();
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Proposed steer");
    await user.click(within(card).getByRole("button", { name: "Send steer" }));

    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(1));
    expect(api.find("POST", STEERS)[0].body).toEqual({
      kind: "add_context",
      text: "Check whether app_v2 writes status values other than completed.",
      hypothesis_id: null,
      proposal_message_id: "a-1",
    });
    expect(await within(card).findByText(/Sent/)).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Send steer" }),
    ).not.toBeInTheDocument();
  });

  it("lets the person edit the proposal before sending", async () => {
    const api = stubProposal();
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Proposed steer");
    await user.click(within(card).getByRole("button", { name: "Edit" }));
    const box = within(card).getByLabelText("Steer text");
    await user.clear(box);
    await user.paste("app_v2 writes COMPLETE in capitals");
    await user.click(within(card).getByRole("button", { name: "Send steer" }));

    await waitFor(() => expect(api.find("POST", STEERS)).toHaveLength(1));
    expect((api.find("POST", STEERS)[0].body as { text: string }).text).toBe(
      "app_v2 writes COMPLETE in capitals",
    );
  });

  it("dismisses the proposal without sending it", async () => {
    const api = stubProposal();
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Proposed steer");
    await user.click(within(card).getByRole("button", { name: "Dismiss" }));

    expect(screen.getByText(/Proposed steer dismissed/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Proposed steer")).not.toBeInTheDocument();
    expect(api.find("POST", STEERS)).toHaveLength(0);
  });

  it("shows who already sent it", async () => {
    stubProposal([
      reply,
      message({
        id: "st-1",
        seq: 6,
        rev: 6,
        kind: "steer",
        author_user_id: "user-2",
        body_md: "**Add context**: Check whether app_v2 writes…",
        payload: {
          investigation_id: INV,
          kind: "add_context",
          hypothesis_id: null,
          proposal_message_id: "a-1",
        },
      }),
    ]);
    renderHub("member");

    const card = await screen.findByLabelText("Proposed steer");
    expect(
      await within(card).findByText(/Sent by Raj Patel/),
    ).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Send steer" }),
    ).not.toBeInTheDocument();
    // The person's steer shows in the thread too.
    expect(
      screen.getByText("steered the investigation", { exact: false }),
    ).toBeInTheDocument();
  });

  it("leaves sending to members", async () => {
    stubProposal();
    renderHub("viewer");

    const card = await screen.findByLabelText("Proposed steer");
    expect(
      within(card).getByText("A member can send this steer."),
    ).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Send steer" }),
    ).not.toBeInTheDocument();
  });
});
