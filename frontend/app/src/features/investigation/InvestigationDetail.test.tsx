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
import { Route, Routes } from "react-router-dom";
import { toast } from "sonner";

import type { OrgRole } from "@/lib/auth/types";
import { FakeEventSource, stubApi, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { InvestigationDetail } from "./InvestigationDetail";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const INV = "inv-1";
const STATE_URL = `/api/v1/investigations/${INV}`;
const REASON =
  "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and restart the API and the worker.";

function state(overrides: Record<string, unknown> = {}) {
  return {
    investigation_id: INV,
    status: "completed",
    issue_id: "issue-42",
    issue_number: 42,
    issue_title: "Completed orders dropped",
    run_number: 7,
    brief: {
      version: 1,
      symptom: "Completed orders dropped 30% on 09-14",
      scope: {
        datasource_id: "ds-1",
        tables: ["analytics.public.orders"],
        time_window: null,
      },
      findings: [{ statement: "Only app_v2 dropped" }],
      ruled_out: [{ statement: "Not region-specific" }],
      leads: ["app_v2 deploy"],
      notes: "The dashboard counts completed only",
    },
    execution_profile: "standard",
    error: null,
    hypotheses: [
      {
        id: "h1",
        title: "app_v2 writes a different status",
        status: "supported",
        reasoning: "The deploy changed the status enum.",
      },
      {
        id: "h2",
        title: "events not landing",
        status: "refuted",
        reasoning: null,
      },
      {
        id: "h3",
        title: "late-arriving events",
        status: "ruled_out",
        reasoning: null,
      },
      {
        id: "h4",
        title: "dedup drops v2 ids",
        status: "untested",
        reasoning: null,
      },
    ],
    main_branch: {
      branch_id: "b-1",
      status: "completed",
      current_step: "synthesize",
      step_history: [],
      matched_patterns: [],
      can_merge: false,
      parent_branch_id: null,
      synthesis: {
        root_cause: "app_v2 writes COMPLETE instead of completed",
        confidence: 0.91,
        causal_chain: ["app_v2 deploy", "status enum changed"],
        estimated_onset: "2026-09-14 09:02 UTC",
        affected_scope: "18,400 app_v2 orders",
        recommendations: ["Backfill app_v2 orders"],
      },
      evidence: [
        {
          hypothesis_id: "h1",
          query: "SELECT status, count(*) FROM orders GROUP BY status",
          result_summary: "COMPLETE 18400",
          row_count: 2,
          supports_hypothesis: true,
          confidence: 0.9,
          interpretation: "app_v2 writes COMPLETE, never completed.",
        },
        {
          hypothesis_id: "h2",
          query: "SELECT count(*) FROM raw.app_events",
          result_summary: "17130",
          row_count: 1,
          supports_hypothesis: false,
          confidence: 0.8,
          interpretation: "v2 events land normally.",
        },
      ],
    },
    user_branch: null,
    ...overrides,
  };
}

const running = () =>
  state({
    status: "running",
    main_branch: {
      ...state().main_branch,
      status: "running",
      current_step: "evaluate_hypotheses",
      synthesis: null,
    },
  });

const failed = () =>
  state({
    status: "failed",
    error: {
      code: "invalid_key",
      message: REASON,
      step: "generate_hypotheses",
    },
    hypotheses: [],
    main_branch: {
      ...state().main_branch,
      status: "failed",
      // Whatever the branch holds, a failed run never shows a conclusion.
      synthesis: {},
      evidence: [],
    },
  });

function renderDetail(
  role: OrgRole,
  body: Record<string, unknown> = state(),
  extra = {},
) {
  const api = stubApi({
    [`GET ${STATE_URL}`]: { body },
    [`GET /api/v1/investigation-feedback/investigations/${INV}`]: { body: [] },
    [`GET ${STATE_URL}/snapshot`]: { body: "archive" },
    ...extra,
  });
  renderAsRole(
    <Routes>
      <Route path="/investigations/:id" element={<InvestigationDetail />} />
      <Route path="/issues/:id" element={<p>Issue thread</p>} />
    </Routes>,
    role,
    `/investigations/${INV}`,
  );
  return api;
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

describe("InvestigationDetail header", () => {
  it("links back to its issue's thread", async () => {
    renderDetail("member");

    expect(
      await screen.findByRole("heading", { name: "Investigation #7" }),
    ).toBeInTheDocument();
    const back = screen.getByRole("link", {
      name: "← #42 Completed orders dropped",
    });
    expect(back).toHaveAttribute("href", "/issues/issue-42");
    expect(screen.getByText("finished")).toBeInTheDocument();
    expect(screen.getByText("standard")).toBeInTheDocument();

    await userEvent.setup().click(back);
    expect(await screen.findByText("Issue thread")).toBeInTheDocument();
  });

  it("has no back link for an imported snapshot, which has no issue", async () => {
    renderDetail(
      "member",
      state({
        issue_id: null,
        issue_number: null,
        issue_title: null,
        run_number: null,
      }),
    );

    expect(
      await screen.findByRole("heading", { name: "Investigation" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /←/ })).not.toBeInTheDocument();
  });

  it("exports the snapshot through the API client", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:snapshot");
    const revokeObjectURL = vi.fn();
    // jsdom has no object URLs.
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });
    const api = renderDetail("viewer");

    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Export snapshot" }));

    await waitFor(() => expect(downloads).toEqual([`snapshot-${INV}.tar.gz`]));
    expect(api.find("GET", `${STATE_URL}/snapshot`)).toHaveLength(1);
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith("/snapshot"));
    expect(
      (call?.[1]?.headers as Record<string, string>).Authorization,
    ).toMatch(/^Bearer /);
    // The archive is saved as it came, not parsed as JSON.
    expect(await createObjectURL.mock.calls[0][0].text()).toBe('"archive"');
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:snapshot");
  });

  it("shares the run by copying its link", async () => {
    renderDetail("viewer");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Share" }));

    expect(await navigator.clipboard.readText()).toBe(
      `${window.location.origin}/investigations/${INV}`,
    );
    expect(toast.success).toHaveBeenCalledWith("Link copied");
    // The mocked user picker is gone.
    expect(screen.queryByText("Alice Chen")).not.toBeInTheDocument();
  });

  it("offers members Add as check, renamed from Codify Test", async () => {
    renderDetail("member");

    expect(
      await screen.findByRole("button", { name: "Add as check" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Codify Test")).not.toBeInTheDocument();
  });

  it.each([
    { confidence: 0.35, verdict: null, offered: false },
    { confidence: 0.35, verdict: "confirmed", offered: true },
    { confidence: 0.91, verdict: "rejected", offered: false },
  ])(
    "offers Add as check at $confidence confidence when the review is $verdict: $offered",
    async ({ confidence, verdict, offered }) => {
      const base = state();
      renderDetail(
        "member",
        state({
          outcome_verdict: verdict,
          main_branch: {
            ...base.main_branch,
            synthesis: { ...base.main_branch.synthesis, confidence },
          },
        }),
      );

      expect(
        await screen.findByRole("heading", { name: "Investigation #7" }),
      ).toBeInTheDocument();
      expect(
        screen.queryAllByRole("button", { name: "Add as check" }),
      ).toHaveLength(offered ? 1 : 0);
    },
  );

  it("keeps viewers from adding checks", async () => {
    renderDetail("viewer");

    expect(
      await screen.findByRole("heading", { name: "Investigation #7" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add as check" }),
    ).not.toBeInTheDocument();
  });
});

describe("InvestigationDetail while running", () => {
  it("lets members cancel, with a compact phase indicator", async () => {
    const api = renderDetail("member", running(), {
      [`POST ${STATE_URL}/cancel`]: {
        body: { investigation_id: INV, status: "cancelled" },
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    expect(await screen.findByText("running · evaluating")).toBeInTheDocument();
    expect(
      screen.queryByText("Investigation Progress"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Root cause")).not.toBeInTheDocument();

    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Cancel run" }));
    await waitFor(() =>
      expect(api.find("POST", `${STATE_URL}/cancel`)).toHaveLength(1),
    );
  });

  it("does not let viewers cancel the run", async () => {
    renderDetail("viewer", running());

    expect(await screen.findByText("running · evaluating")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel run" }),
    ).not.toBeInTheDocument();
  });

  it("no longer offers the old chat box or branch flow", async () => {
    renderDetail("member", running());

    expect(
      await screen.findByRole("button", { name: "Cancel run" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Collaborate")).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Ask a question or provide direction..."),
    ).not.toBeInTheDocument();
  });
});

describe("InvestigationDetail body", () => {
  it("shows the brief the run was given", async () => {
    renderDetail("viewer");

    const brief = await screen.findByRole("region", { name: "Brief" });
    expect(
      within(brief).getByText("Completed orders dropped 30% on 09-14"),
    ).toBeInTheDocument();
    expect(within(brief).getByText("Only app_v2 dropped")).toBeInTheDocument();
    expect(within(brief).getByText("Not region-specific")).toBeInTheDocument();
    expect(within(brief).getByText("app_v2 deploy")).toBeInTheDocument();
    expect(
      within(brief).getByText("analytics.public.orders"),
    ).toBeInTheDocument();
  });

  it("lists each hypothesis with how it ended and its evidence", async () => {
    renderDetail("viewer");
    const user = userEvent.setup();

    const h1 = await screen.findByRole("listitem", {
      name: "Hypothesis app_v2 writes a different status",
    });
    expect(within(h1).getByText("supported")).toBeInTheDocument();
    expect(
      within(h1).getByText("The deploy changed the status enum."),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("listitem", {
          name: "Hypothesis late-arriving events",
        }),
      ).getByText("ruled out by a person"),
    ).toBeInTheDocument();
    const untested = within(
      screen.getByRole("listitem", { name: "Hypothesis dedup drops v2 ids" }),
    ).getByText("untested");
    expect(untested.className).toContain("amber");

    // Queries collapse like the thread's tool calls.
    const toggle = within(h1).getByRole("button", {
      name: "Ran 1 query · 2 rows",
    });
    expect(within(h1).queryByText(/SELECT status/)).not.toBeInTheDocument();
    await user.click(toggle);
    expect(
      within(h1).getByText(
        "SELECT status, count(*) FROM orders GROUP BY status",
      ),
    ).toBeInTheDocument();
    expect(within(h1).getByText("COMPLETE 18400")).toBeInTheDocument();
    expect(
      within(h1).getByText("app_v2 writes COMPLETE, never completed."),
    ).toBeInTheDocument();
    expect(within(h1).getByText("Supports")).toBeInTheDocument();
  });

  it("shows the outcome in the thread's style", async () => {
    renderDetail("viewer");

    const outcome = await screen.findByRole("region", { name: "Outcome" });
    expect(within(outcome).getByText("Root cause")).toBeInTheDocument();
    expect(within(outcome).getByText("confidence 0.91")).toBeInTheDocument();
    expect(
      within(outcome).getByText("app_v2 writes COMPLETE instead of completed"),
    ).toBeInTheDocument();
    expect(
      within(outcome).getByText("H3 ruled out by a person"),
    ).toBeInTheDocument();
    expect(within(outcome).getByText("app_v2 deploy")).toBeInTheDocument();
    expect(
      within(outcome).getByText("status enum changed"),
    ).toBeInTheDocument();
    expect(
      within(outcome).getByText("2026-09-14 09:02 UTC"),
    ).toBeInTheDocument();
    expect(
      within(outcome).getByText("18,400 app_v2 orders"),
    ).toBeInTheDocument();
    expect(
      within(outcome).getByText("Backfill app_v2 orders"),
    ).toBeInTheDocument();
  });
});

describe("InvestigationDetail for a failed run", () => {
  it("says why it failed and what to do instead of a conclusion", async () => {
    renderDetail("member", failed());

    const outcome = await screen.findByRole("region", { name: "Outcome" });
    expect(within(outcome).getByText(REASON)).toBeInTheDocument();
    expect(
      within(outcome).getByText("while generating hypotheses"),
    ).toBeInTheDocument();
    expect(within(outcome).getByText(/Once it's fixed/)).toBeInTheDocument();
    expect(
      within(outcome).getByRole("link", { name: "Retry from the issue →" }),
    ).toHaveAttribute("href", "/issues/issue-42");
    expect(screen.getAllByText("failed").length).toBeGreaterThan(0);
    expect(
      screen.queryByText(/Unable to determine a definitive root cause/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Root cause")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add as check" }),
    ).not.toBeInTheDocument();
  });
});
