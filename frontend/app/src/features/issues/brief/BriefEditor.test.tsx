import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";

import { FakeEventSource, stubRadixDom } from "@/test/api";

import {
  MESSAGES,
  RUNS,
  THREAD,
  THREADS,
  message,
  renderHub,
  stubHub,
} from "../hub/test-helpers";
import { briefFromForm, continuationBrief, formFromBrief } from "./brief-form";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const BRIEF_DRAFTS = `${THREADS}/${THREAD}/brief-drafts`;

const rajComment = message({
  id: "c-raj",
  seq: 1,
  rev: 1,
  author_user_id: "user-2",
  body_md: "My dashboard counts status = 'completed' only",
});

const queuedBrief = message({
  id: "b-1",
  seq: 2,
  rev: 2,
  author_kind: "agent",
  author_user_id: null,
  requested_by_user_id: "user-1",
  kind: "brief",
  status: "queued",
});

const draftedBrief = {
  version: 1,
  symptom: "Completed orders dropped about 30% on 2026-09-14",
  scope: {
    datasource_id: "ds-1",
    tables: ["analytics.public.orders"],
    time_window: null,
  },
  findings: [
    {
      statement: "The drop is only in orders with source = app_v2",
      message_id: "c-raj",
      query_result_id: null,
    },
    { statement: "Web orders are flat", message_id: null },
  ],
  ruled_out: [{ statement: "Not region-specific", message_id: null }],
  leads: ["app_v2 deploy on 2026-09-14"],
  notes: "The dashboard counts status = 'completed' only",
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

describe("Brief editor", () => {
  it("drafts a brief, lets the person edit it and starts the run", async () => {
    const api = stubHub([rajComment], {
      [`POST ${BRIEF_DRAFTS}`]: { status: 201, body: queuedBrief },
      [`POST ${RUNS}`]: { status: 201, body: {} },
    });
    const user = userEvent.setup();
    renderHub("member");

    await user.click(
      await screen.findByRole("button", { name: /Investigate…/ }),
    );
    await waitFor(() => expect(api.find("POST", BRIEF_DRAFTS)).toHaveLength(1));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/drafting a brief from the thread/),
    ).toBeInTheDocument();

    // The draft arrives over the thread stream.
    await waitFor(() =>
      expect(FakeEventSource.instances.length).toBeGreaterThan(0),
    );
    act(() => {
      for (const stream of FakeEventSource.instances) {
        stream.emit("message", {
          ...queuedBrief,
          rev: 5,
          status: "complete",
          body_md: "**Investigation brief**",
          payload: { brief: draftedBrief },
        });
      }
    });

    const symptom = await within(dialog).findByLabelText("Symptom");
    expect(symptom).toHaveValue(draftedBrief.symptom);
    expect(within(dialog).getByLabelText("finding 1")).toHaveValue(
      "The drop is only in orders with source = app_v2",
    );

    // Findings link to the message they came from.
    await user.click(
      within(dialog).getByRole("button", { name: /from Raj Patel's message/ }),
    );
    expect(
      within(dialog).getByText("My dashboard counts status = 'completed' only"),
    ).toBeInTheDocument();

    await user.clear(symptom);
    await user.click(symptom);
    await user.paste("Completed orders -30% on 09-14");
    await user.click(within(dialog).getByLabelText("Include finding 2"));
    await user.click(within(dialog).getByRole("button", { name: "Add lead" }));
    await user.click(within(dialog).getByLabelText("Lead 2"));
    await user.paste("dedup step");
    await user.selectOptions(within(dialog).getByLabelText("Depth"), "deep");
    await user.selectOptions(
      within(dialog).getByLabelText("Datasource"),
      "ds-2",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() => expect(api.find("POST", RUNS)).toHaveLength(1));
    expect(api.find("POST", RUNS)[0].body).toEqual({
      brief: {
        version: 1,
        symptom: "Completed orders -30% on 09-14",
        scope: {
          datasource_id: "ds-2",
          tables: ["analytics.public.orders"],
          time_window: null,
        },
        findings: [
          {
            statement: "The drop is only in orders with source = app_v2",
            message_id: "c-raj",
            query_result_id: null,
          },
        ],
        ruled_out: [
          {
            statement: "Not region-specific",
            message_id: null,
            query_result_id: null,
          },
        ],
        leads: ["app_v2 deploy on 2026-09-14", "dedup step"],
        notes: "The dashboard counts status = 'completed' only",
      },
      execution_profile: "deep",
      dataset_id: "analytics.public.orders",
      datasource_id: "ds-2",
      source_thread_id: THREAD,
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(toast.success).toHaveBeenCalledWith(
      "Investigation started",
      expect.anything(),
    );
  });

  it("falls back to writing the brief when drafting fails", async () => {
    stubHub([rajComment], {
      [`POST ${BRIEF_DRAFTS}`]: {
        status: 201,
        body: {
          ...queuedBrief,
          status: "error",
          payload: {
            error: "The agent is unavailable right now. Try again shortly.",
          },
        },
      },
      [`GET ${MESSAGES}`]: {
        body: {
          items: [
            rajComment,
            {
              ...queuedBrief,
              status: "error",
              payload: {
                error: "The agent is unavailable right now. Try again shortly.",
              },
            },
          ],
        },
      },
    });
    const user = userEvent.setup();
    renderHub("member");

    await user.click(
      await screen.findByRole("button", { name: /Investigate…/ }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText(/The agent is unavailable right now/),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Symptom")).toHaveValue(
      "Completed orders dropped",
    );
  });

  it("requires a symptom before starting", async () => {
    const api = stubHub([rajComment], {
      [`POST ${BRIEF_DRAFTS}`]: { status: 201, body: queuedBrief },
    });
    const user = userEvent.setup();
    renderHub("member");

    await user.click(
      await screen.findByRole("button", { name: /Investigate…/ }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Write it myself" }),
    );
    const symptom = within(dialog).getByLabelText("Symptom");
    await user.clear(symptom);
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "the symptom is required",
    );
    expect(api.find("POST", RUNS)).toHaveLength(0);
  });

  it("is not offered to viewers", async () => {
    stubHub([rajComment]);
    renderHub("viewer");

    expect(
      await screen.findByText("My dashboard counts status = 'completed' only"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Investigate…/ }),
    ).not.toBeInTheDocument();
  });
});

describe("brief form", () => {
  it("round-trips a brief with a UTC time window", () => {
    const brief = {
      symptom: "x",
      scope: {
        datasource_id: null,
        tables: ["a", "b"],
        time_window: {
          from: "2026-09-10T00:00:00Z",
          to: "2026-09-16T12:30:00Z",
        },
      },
      findings: [],
      ruled_out: [],
      leads: ["", "lead"],
      notes: "",
    };
    expect(briefFromForm(formFromBrief(brief))).toEqual({
      version: 1,
      ...brief,
      leads: ["lead"],
    });
  });

  it("seeds a follow-up with the prior conclusion and an empty lead", () => {
    const prior = { symptom: "x", findings: [], leads: ["a"] };
    expect(continuationBrief(prior, "app_v2 writes COMPLETE")).toMatchObject({
      findings: [
        { statement: "The previous run concluded: app_v2 writes COMPLETE" },
      ],
      leads: ["a", ""],
    });
    expect(
      continuationBrief(prior, "late events", { note: "they arrive in 5 min" }),
    ).toMatchObject({
      findings: [],
      ruled_out: [
        {
          statement:
            'The previous run concluded "late events", which was rejected: they arrive in 5 min',
        },
      ],
    });
  });
});
