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
  RUNS,
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

const started = message({
  id: "i-1",
  seq: 3,
  rev: 3,
  kind: "investigation",
  body_md: "Started an investigation: Completed orders dropped 30%",
  payload: {
    investigation_id: INV,
    run_id: "run-1",
    execution_profile: "standard",
    brief: run().brief,
    source_thread_id: THREAD,
    parent_run_id: null,
  },
});

const outcomeMessage = message({
  id: "o-1",
  seq: 9,
  rev: 9,
  kind: "investigation",
  author_kind: "agent",
  author_user_id: null,
  body_md: "**Investigation finished**",
  payload: {
    phase: "outcome",
    outcome_for: INV,
    investigation_id: INV,
    run_id: "run-1",
    outcome: {
      status: "completed",
      root_cause: "app_v2 writes COMPLETE instead of completed",
      confidence: 0.91,
      recommendations: ["Backfill app_v2 orders"],
      supporting_evidence: ["18,400 app_v2 rows have status COMPLETE"],
      hypotheses: [
        {
          id: "h1",
          title: "app_v2 writes a different status",
          status: "supported",
        },
        { id: "h2", title: "events not landing", status: "refuted" },
        { id: "h3", title: "late-arriving events", status: "ruled_out" },
        { id: "h4", title: "dedup drops v2 ids", status: "untested" },
      ],
      counter_analysis: null,
    },
  },
});

const runningStatus = {
  investigation_id: INV,
  workflow_status: "running",
  current_step: "evaluate_hypotheses",
  progress: 0.62,
  is_complete: false,
  hypotheses: [
    {
      id: "h1",
      title: "app_v2 writes a different status",
      status: "supported",
    },
    { id: "h2", title: "events not landing", status: "running" },
  ],
  pending_steers: [],
};

const completedStatus = {
  investigation_id: INV,
  workflow_status: "completed",
  current_step: null,
  hypotheses: null,
};

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

describe("Investigation card", () => {
  it("shows the live phase and the hypotheses being tested", async () => {
    stubHub([started], {
      [`GET ${INVESTIGATION}/status`]: { body: runningStatus },
      [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    expect(
      await within(card).findByText("running · evaluating"),
    ).toBeInTheDocument();
    expect(within(card).getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "62",
    );
    const h1 = within(card).getByLabelText(
      "Hypothesis app_v2 writes a different status",
    );
    expect(within(h1).getByText("supported")).toBeInTheDocument();
    const h2 = within(card).getByLabelText("Hypothesis events not landing");
    expect(within(h2).getByText("testing")).toBeInTheDocument();

    await userEvent
      .setup()
      .click(within(card).getByRole("button", { name: "view brief" }));
    expect(within(card).getByText("Only app_v2 dropped")).toBeInTheDocument();
  });

  it("is numbered among the issue's runs and links to the run's details", async () => {
    stubHub([started], {
      [`GET ${INVESTIGATION}/status`]: { body: runningStatus },
      [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
      [`GET ${RUNS}`]: {
        body: {
          items: [run({ number: 2, status: "running", completed_at: null })],
          total: 1,
        },
      },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    expect(
      await within(card).findByRole("heading", { name: "Investigation #2" }),
    ).toBeInTheDocument();
    expect(within(card).getByText("standard")).toBeInTheDocument();
    expect(
      within(card).getByRole("link", { name: "details →" }),
    ).toHaveAttribute("href", `/investigations/${INV}`);
    expect(
      within(card).queryByRole("link", { name: /Open/ }),
    ).not.toBeInTheDocument();
    // The brief reads like the mockup's one-liner.
    expect(
      within(card).getByText(
        /Brief: Completed orders dropped 30% · Only app_v2 dropped · lead: app_v2 deploy\./,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/started an investigation/, { exact: false }),
    ).toBeInTheDocument();
  });

  it("attributes a run nobody started by hand to dataing", async () => {
    stubHub(
      [
        {
          ...started,
          author_kind: "system",
          author_user_id: null,
        },
      ],
      {
        [`GET ${INVESTIGATION}/status`]: { body: runningStatus },
        [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
      },
    );
    renderHub("member");

    await screen.findByLabelText("Investigation");
    const meta = screen.getByText(/started an investigation/);
    expect(meta).toHaveTextContent(/^dataing · started an investigation · /);
  });

  it("shows how each hypothesis ended once the run finished", async () => {
    stubHub([started, outcomeMessage], {
      [`GET ${INVESTIGATION}/status`]: { body: completedStatus },
      [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
      [`GET ${RUNS}`]: { body: { items: [run()], total: 1 } },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    expect(await within(card).findByText("finished")).toBeInTheDocument();
    const h3 = within(card).getByLabelText("Hypothesis late-arriving events");
    expect(within(h3).getByText("ruled out by a person")).toBeInTheDocument();
    expect(within(card).queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("Outcome card", () => {
  function stubOutcome(extra = {}) {
    return stubHub([started, outcomeMessage], {
      [`GET ${INVESTIGATION}/status`]: { body: completedStatus },
      [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
      [`GET ${RUNS}`]: { body: { items: [run()], total: 1 } },
      ...extra,
    });
  }

  it("shows the root cause and how each hypothesis ended", async () => {
    stubOutcome();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    expect(
      within(card).getByText("app_v2 writes COMPLETE instead of completed"),
    ).toBeInTheDocument();
    expect(within(card).getByText("confidence 0.91")).toBeInTheDocument();
    expect(
      within(card).getByText("H2 refuted by evidence"),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("H3 ruled out by a person"),
    ).toBeInTheDocument();
    expect(within(card).getByText("H4 untested")).toBeInTheDocument();
    expect(
      within(card).getByText("18,400 app_v2 rows have status COMPLETE"),
    ).toBeInTheDocument();
  });

  it("confirms the root cause", async () => {
    const api = stubOutcome({
      [`POST ${INVESTIGATION}/outcome-review`]: {
        body: run({ outcome_verdict: "confirmed" }),
      },
    });
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    await user.click(within(card).getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(api.find("POST", `${INVESTIGATION}/outcome-review`)).toHaveLength(
        1,
      ),
    );
    expect(api.find("POST", `${INVESTIGATION}/outcome-review`)[0].body).toEqual(
      { verdict: "confirmed", note: null },
    );
    expect(toast.success).toHaveBeenCalledWith(
      "Root cause confirmed",
      expect.anything(),
    );
  });

  it("asks why before rejecting", async () => {
    const api = stubOutcome({
      [`POST ${INVESTIGATION}/outcome-review`]: {
        body: run({ outcome_verdict: "rejected" }),
      },
    });
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    await user.click(within(card).getByRole("button", { name: "Reject" }));
    const send = within(card).getByRole("button", { name: "Reject outcome" });
    expect(send).toBeDisabled();

    await user.click(within(card).getByLabelText("Why is this wrong?"));
    await user.paste("v1 dropped too");
    await user.click(send);

    await waitFor(() =>
      expect(api.find("POST", `${INVESTIGATION}/outcome-review`)).toHaveLength(
        1,
      ),
    );
    expect(api.find("POST", `${INVESTIGATION}/outcome-review`)[0].body).toEqual(
      { verdict: "rejected", note: "v1 dropped too" },
    );
  });

  it("continues investigating from the run's brief and conclusion", async () => {
    const api = stubOutcome({
      [`POST ${RUNS}`]: { status: 201, body: run({ id: "run-2" }) },
    });
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    await user.click(
      within(card).getByRole("button", { name: "Continue investigating" }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Continue investigating" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText("finding 2")).toHaveValue(
      "The previous run concluded: app_v2 writes COMPLETE instead of completed",
    );
    const lead = within(dialog).getByLabelText("Lead 2");
    expect(lead).toHaveValue("");
    await user.click(lead);
    await user.paste("check the backfill job");
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() => expect(api.find("POST", RUNS)).toHaveLength(1));
    const body = api.find("POST", RUNS)[0].body as {
      brief: { leads: string[] };
      parent_run_id: string;
      source_thread_id: string;
    };
    expect(body.parent_run_id).toBe("run-1");
    expect(body.source_thread_id).toBe(THREAD);
    expect(body.brief.leads).toEqual([
      "app_v2 deploy",
      "check the backfill job",
    ]);
  });

  it("turns the finding into a check", async () => {
    const api = stubOutcome({
      [`POST ${INVESTIGATION}/codify`]: {
        body: {
          investigation_id: INV,
          format: "sql",
          content: "SELECT count(*) FROM orders WHERE status = 'COMPLETE'",
          tests: [],
          confidence: 0.91,
        },
      },
    });
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    await user.click(
      within(card).getByRole("button", { name: "Add as check" }),
    );

    await waitFor(() =>
      expect(api.find("POST", `${INVESTIGATION}/codify`)).toHaveLength(1),
    );
    expect(api.find("POST", `${INVESTIGATION}/codify`)[0].body).toEqual({
      format: "sql",
    });
  });

  describe("a root cause below 60% confidence", () => {
    const weakOutcome = {
      ...outcomeMessage,
      payload: {
        ...outcomeMessage.payload,
        outcome: {
          ...(outcomeMessage.payload.outcome as object),
          confidence: 0.35,
        },
      },
    };
    const reviewed = (review: Record<string, unknown>) =>
      run({
        outcome_reviewed_by: "user-2",
        outcome_reviewed_at: "2026-09-14T08:50:00Z",
        ...review,
      });

    function stubWeak(runRecord = run(), extra = {}) {
      return stubHub([started, weakOutcome], {
        [`GET ${INVESTIGATION}/status`]: { body: completedStatus },
        [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
        [`GET ${RUNS}`]: { body: { items: [runRecord], total: 1 } },
        ...extra,
      });
    }

    it("says it needs confirming before it can become a check", async () => {
      stubWeak();
      renderHub("member");

      const card = await screen.findByLabelText("Investigation outcome");
      const button = within(card).getByRole("button", { name: "Add as check" });
      expect(button).toBeDisabled();
      expect(button).toHaveAccessibleDescription(
        "The root cause's confidence (35%) is below 60%. Confirm it to add it as a check.",
      );
    });

    it("can become a check once someone confirms it", async () => {
      const api = stubWeak(reviewed({ outcome_verdict: "confirmed" }), {
        [`POST ${INVESTIGATION}/codify`]: {
          body: {
            investigation_id: INV,
            format: "sql",
            content: "SELECT count(*) FROM orders WHERE status = 'COMPLETE'",
            tests: [],
            confidence: 0.35,
          },
        },
      });
      const user = userEvent.setup();
      renderHub("member");

      const card = await screen.findByLabelText("Investigation outcome");
      await within(card).findByText("Confirmed by Raj Patel");
      await user.click(
        within(card).getByRole("button", { name: "Add as check" }),
      );

      await waitFor(() =>
        expect(api.find("POST", `${INVESTIGATION}/codify`)).toHaveLength(1),
      );
    });
  });

  it("doesn't offer a rejected root cause as a check", async () => {
    stubOutcome({
      [`GET ${RUNS}`]: {
        body: {
          items: [
            run({
              outcome_verdict: "rejected",
              outcome_note: "It's the dedup job",
              outcome_reviewed_by: "user-2",
              outcome_reviewed_at: "2026-09-14T08:50:00Z",
            }),
          ],
          total: 1,
        },
      },
    });
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    await within(card).findByText(/Rejected by Raj Patel/);
    expect(
      within(card).queryByRole("button", { name: "Add as check" }),
    ).not.toBeInTheDocument();
  });

  it("warns when the check of the conclusion didn't run", async () => {
    stubHub(
      [
        started,
        {
          ...outcomeMessage,
          payload: {
            ...outcomeMessage.payload,
            outcome: {
              ...(outcomeMessage.payload.outcome as object),
              counter_analysis: { error: "Anthropic is overloaded (529)." },
            },
          },
        },
      ],
      {
        [`GET ${INVESTIGATION}/status`]: { body: completedStatus },
        [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
        [`GET ${RUNS}`]: { body: { items: [run()], total: 1 } },
      },
    );
    renderHub("member");

    const card = await screen.findByLabelText("Investigation outcome");
    expect(
      within(card).getByText(
        "The check of this conclusion didn't run: Anthropic is overloaded (529).",
      ),
    ).toBeInTheDocument();
  });

  it("shows the review to viewers without the actions", async () => {
    stubOutcome({
      [`GET ${RUNS}`]: {
        body: {
          items: [
            run({
              outcome_verdict: "confirmed",
              outcome_reviewed_by: "user-2",
              outcome_reviewed_at: "2026-09-14T08:50:00Z",
            }),
          ],
          total: 1,
        },
      },
    });
    renderHub("viewer");

    const card = await screen.findByLabelText("Investigation outcome");
    expect(
      await within(card).findByText("Confirmed by Raj Patel"),
    ).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Confirm" }),
    ).not.toBeInTheDocument();
  });
});

describe("A failed run", () => {
  const REASON =
    "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and restart the API and the worker.";

  const failedOutcome = message({
    ...outcomeMessage,
    payload: {
      phase: "outcome",
      outcome_for: INV,
      investigation_id: INV,
      run_id: "run-1",
      outcome: {
        status: "failed",
        error: {
          code: "invalid_key",
          message: REASON,
          step: "generate_hypotheses",
        },
      },
    },
  });

  const failedRun = run({
    status: "failed",
    error: REASON,
    confidence: null,
    synthesis_summary: null,
  });

  function stubFailed(messages = [started, failedOutcome], extra = {}) {
    return stubHub(messages, {
      [`GET ${INVESTIGATION}/status`]: {
        body: { investigation_id: INV, workflow_status: "failed" },
      },
      [`GET ${INVESTIGATION}/steers`]: { body: { items: [] } },
      [`GET ${RUNS}`]: { body: { items: [failedRun], total: 1 } },
      ...extra,
    });
  }

  it("says why it failed instead of a root cause, and offers Retry", async () => {
    stubFailed();
    const user = userEvent.setup();
    renderHub("member");

    const outcome = await screen.findByLabelText("Investigation outcome");
    expect(within(outcome).getByText("failed")).toBeInTheDocument();
    expect(within(outcome).getByText(REASON)).toBeInTheDocument();
    expect(
      within(outcome).getByText("while generating hypotheses"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/root cause/i)).not.toBeInTheDocument();
    expect(
      await screen.findByText(/investigation #1 failed/),
    ).toBeInTheDocument();

    // The start card turns failed with the reason; the outcome carries Retry.
    const card = screen.getByLabelText("Investigation");
    expect(within(card).getByText("failed")).toBeInTheDocument();
    expect(within(card).getByText(REASON)).toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();

    await user.click(within(outcome).getByRole("button", { name: "Retry" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Hand off to an investigation",
    });
    expect(within(dialog).getByLabelText("Symptom")).toHaveValue(
      "Completed orders dropped 30%",
    );
    expect(within(dialog).getByLabelText("finding 1")).toHaveValue(
      "Only app_v2 dropped",
    );
  });

  it("offers Retry on the card when the run failed without an outcome", async () => {
    stubFailed([started]);
    const user = userEvent.setup();
    renderHub("member");

    const card = await screen.findByLabelText("Investigation");
    expect(await within(card).findByText("failed")).toBeInTheDocument();
    expect(await within(card).findByText(REASON)).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("dialog", {
        name: "Hand off to an investigation",
      }),
    ).toBeInTheDocument();
  });

  it("leaves Retry to members", async () => {
    stubFailed();
    renderHub("viewer");

    const outcome = await screen.findByLabelText("Investigation outcome");
    expect(within(outcome).getByText(REASON)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
  });
});
