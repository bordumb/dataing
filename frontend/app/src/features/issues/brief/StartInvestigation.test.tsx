import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useParams } from "react-router-dom";
import { toast } from "sonner";

import type { OrgRole } from "@/lib/auth/types";
import { stubApi, stubRadixDom, type StubResponse } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import {
  InvestigateButton,
  type InvestigationPrefill,
} from "./StartInvestigation";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const START = "/api/v1/investigations";

function datasource(id: string, name: string) {
  return {
    id,
    name,
    type: "postgres",
    category: "database",
    is_active: true,
    is_default: id === "ds-1",
    status: "connected",
    created_at: "2026-01-01T00:00:00Z",
  };
}

const ONE_DATASOURCE = {
  body: { items: [datasource("ds-1", "warehouse")], total: 1 },
};
const TWO_DATASOURCES = {
  body: {
    items: [datasource("ds-1", "warehouse"), datasource("ds-2", "lake")],
    total: 2,
  },
};

const STARTED = {
  status: 200,
  body: {
    investigation_id: "inv-9",
    run_id: "run-9",
    issue_id: "issue-9",
    issue_number: 12,
    status: "queued",
    main_branch_id: "branch-9",
  },
};

function IssueLanding() {
  const { id } = useParams();
  return <p>Issue page {id}</p>;
}

function renderStart(
  role: OrgRole,
  {
    datasources = ONE_DATASOURCE,
    start = STARTED,
    prefill,
    routes = {},
  }: {
    datasources?: StubResponse;
    start?: StubResponse;
    prefill?: InvestigationPrefill;
    routes?: Record<string, StubResponse>;
  } = {},
) {
  const api = stubApi({
    "GET /api/v1/datasources": datasources,
    [`POST ${START}`]: start,
    ...routes,
  });
  renderAsRole(
    <Routes>
      <Route
        path="/"
        element={
          <>
            <p>Dashboard</p>
            <InvestigateButton prefill={prefill} />
          </>
        }
      />
      <Route path="/issues/:id" element={<IssueLanding />} />
    </Routes>,
    role,
  );
  return api;
}

async function openDialog() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Investigate…" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Start an investigation",
  });
  return { user, dialog };
}

beforeAll(() => stubRadixDom());

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Investigate…", () => {
  it("is only offered to members", async () => {
    renderStart("viewer");

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Investigate…" }),
    ).not.toBeInTheDocument();
  });

  it("opens the brief editor in new mode with nothing to draft from", async () => {
    renderStart("member");
    const { dialog } = await openDialog();

    expect(within(dialog).getByLabelText("Symptom")).toHaveValue("");
    expect(within(dialog).getByLabelText("Table")).toHaveValue("");
    // Findings and exclusions start empty; there is no thread to draft from,
    // so there are no leads to test first either.
    expect(within(dialog).getAllByText("None yet.")).toHaveLength(2);
    expect(within(dialog).queryByText(/Leads/)).not.toBeInTheDocument();
    // The only datasource is preselected, and nothing defers to an issue.
    const select = within(dialog).getByLabelText("Datasource");
    await waitFor(() => expect(select).toHaveValue("ds-1"));
    expect(
      within(dialog).queryByRole("option", { name: "The issue's datasource" }),
    ).not.toBeInTheDocument();
  });

  it("requires a symptom and at least one table", async () => {
    const api = renderStart("member");
    const { user, dialog } = await openDialog();
    const start = within(dialog).getByRole("button", {
      name: "Start investigation",
    });

    await user.click(start);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "the symptom is required",
    );

    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike in orders.email");
    await user.click(start);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "Pick at least one table",
    );
    expect(api.find("POST", START)).toHaveLength(0);
  });

  it("starts on the default datasource and lets the person pick another", async () => {
    const api = renderStart("member", { datasources: TWO_DATASOURCES });
    const { user, dialog } = await openDialog();

    const select = within(dialog).getByLabelText("Datasource");
    await within(dialog).findByRole("option", { name: /lake/ });
    await waitFor(() => expect(select).toHaveValue("ds-1"));
    await user.selectOptions(select, "ds-2");
    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike in orders.email");
    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("public.orders");
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() => expect(api.find("POST", START)).toHaveLength(1));
    const body = api.find("POST", START)[0].body as {
      datasource_id: string;
      brief: { scope: { datasource_id: string } };
    };
    expect([body.datasource_id, body.brief.scope.datasource_id]).toEqual([
      "ds-2",
      "ds-2",
    ]);
  });

  it("looks tables up as the person types, like the old investigation page", async () => {
    renderStart("member", {
      routes: {
        "GET /api/v1/datasources/ds-1/schema": {
          body: {
            catalogs: [
              {
                name: "demo",
                schemas: [
                  {
                    name: "public",
                    tables: [
                      {
                        name: "orders",
                        native_path: "public.orders",
                        columns: [{ name: "id" }, { name: "email" }],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        },
      },
    });
    const { user, dialog } = await openDialog();
    await waitFor(() =>
      expect(within(dialog).getByLabelText("Datasource")).toHaveValue("ds-1"),
    );

    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("ord");
    await user.click(
      await within(dialog).findByRole("button", { name: /public\.orders/ }),
    );

    expect(within(dialog).getByLabelText("Table")).toHaveValue("public.orders");
  });

  it("sends the days picked in the date picker as the time window", async () => {
    const api = renderStart("member");
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike in orders.email");
    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("public.orders");
    await user.click(within(dialog).getByRole("button", { name: /Any time/ }));
    await user.click(
      await within(dialog).findByRole("button", { name: "Today" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() => expect(api.find("POST", START)).toHaveLength(1));
    const now = new Date();
    const day = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T00:00:00Z`;
    const tomorrow = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + 1,
    );
    expect(
      (
        api.find("POST", START)[0].body as {
          brief: { scope: { time_window: unknown } };
        }
      ).brief.scope.time_window,
    ).toEqual({ from: day(now), to: day(tomorrow) });
  });

  it("starts the run and lands on its new issue", async () => {
    const api = renderStart("member");
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike in orders.email");
    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("public.orders");
    await user.click(
      within(dialog).getByRole("button", { name: "Add another table" }),
    );
    await user.click(within(dialog).getAllByLabelText("Table")[1]);
    await user.paste("public.customers");
    await user.selectOptions(within(dialog).getByLabelText("Depth"), "deep");
    // A run investigates one datasource, so every table row shows it
    await waitFor(() =>
      expect(
        within(dialog)
          .getAllByLabelText("Datasource")
          .map((select) => (select as HTMLSelectElement).value),
      ).toEqual(["ds-1", "ds-1"]),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    expect(await screen.findByText("Issue page issue-9")).toBeInTheDocument();
    expect(api.find("POST", START)[0].body).toEqual({
      brief: {
        version: 1,
        symptom: "Null spike in orders.email",
        scope: {
          datasource_id: "ds-1",
          tables: ["public.orders", "public.customers"],
          time_window: null,
        },
        findings: [],
        ruled_out: [],
        leads: [],
        notes: "",
      },
      execution_profile: "deep",
      datasource_id: "ds-1",
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith(
      "Investigation started in issue #12",
      expect.anything(),
    );
  });

  it("asks for a datasource when the server can't tell which to use", async () => {
    renderStart("member", {
      start: {
        status: 409,
        body: {
          detail: {
            error: "ambiguous_datasource",
            message: "Multiple datasources match. Please specify which to use.",
          },
        },
      },
    });
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike in orders.email");
    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("public.orders");
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    expect(
      await within(dialog).findByText(/Pick the one to investigate/),
    ).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith(
      "Couldn't start the investigation",
      {
        description: "Multiple datasources match. Please specify which to use.",
      },
    );
  });

  it("shows the server's message when starting fails", async () => {
    renderStart("member", {
      start: { status: 400, body: { detail: "Unknown table public.nope" } },
    });
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByLabelText("Symptom"));
    await user.paste("Null spike");
    await user.click(within(dialog).getByLabelText("Table"));
    await user.paste("public.nope");
    await user.click(
      within(dialog).getByRole("button", { name: "Start investigation" }),
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Couldn't start the investigation",
        { description: "Unknown table public.nope" },
      ),
    );
    // The person keeps what they wrote.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Symptom")).toHaveValue("Null spike");
  });

  it("starts from what the page knows", async () => {
    renderStart("member", {
      datasources: TWO_DATASOURCES,
      prefill: { tables: ["analytics.orders"], datasourceId: "ds-2" },
    });
    const { dialog } = await openDialog();

    expect(within(dialog).getByLabelText("Table")).toHaveValue(
      "analytics.orders",
    );
    await within(dialog).findByRole("option", { name: /lake/ });
    expect(within(dialog).getByLabelText("Datasource")).toHaveValue("ds-2");
  });
});
