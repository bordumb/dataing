import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes } from "react-router-dom";
import { toast } from "sonner";

import { stubApi, type StubResponse } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { DatasourceCredentialsPage } from "./datasource-credentials-page";

vi.mock("sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("sonner")>()),
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const DATASOURCE = "/api/v1/datasources/ds-1";
const CREDENTIALS = `${DATASOURCE}/credentials`;
const PAGE = "/settings/datasources/ds-1/credentials";
const TEST_PASSWORD = "s3cret"; // pragma: allowlist secret

function sourceType(type: string, fields: string[]) {
  return {
    type,
    display_name: type,
    category: "database",
    icon: type,
    description: "",
    capabilities: {},
    config_schema: {
      field_groups: [],
      fields: fields.map((name) => ({
        name,
        label: name,
        type: "string",
        required: false,
        group: "connection",
      })),
    },
  };
}

const SOURCE_TYPES = {
  body: {
    types: [
      sourceType("postgres", ["host", "database", "username", "password"]),
      sourceType("snowflake", ["account", "username", "role", "warehouse"]),
      sourceType("local_file", ["path"]),
    ],
  },
};

function renderPage({
  type = "postgres",
  status = { body: { configured: false } },
  test = { body: { success: true, tables_accessible: 12 } },
  route = "/issues/issue-1",
}: {
  type?: string;
  status?: StubResponse;
  test?: StubResponse;
  route?: string;
} = {}) {
  const api = stubApi({
    [`GET ${DATASOURCE}`]: {
      body: { id: "ds-1", name: "prod", type, status: "connected" },
    },
    "GET /api/v1/datasources/types": SOURCE_TYPES,
    [`GET ${CREDENTIALS}`]: status,
    [`POST ${CREDENTIALS}/test`]: test,
    [`POST ${CREDENTIALS}`]: {
      status: 201,
      body: { configured: true, db_username: "demo" },
    },
    [`DELETE ${CREDENTIALS}`]: { body: { deleted: true } },
  });
  renderAsRole(
    <Routes>
      <Route
        path="/issues/:id"
        element={
          <>
            <p>Issue thread</p>
            <Link to={PAGE}>Add your login</Link>
          </>
        }
      />
      <Route
        path="/settings/datasources/:datasourceId/credentials"
        element={<DatasourceCredentialsPage />}
      />
      <Route path="/datasources" element={<p>Datasources</p>} />
    </Routes>,
    "member",
    route,
  );
  return api;
}

/** Follow the agent's link from the issue thread to the page. */
async function openFromThread() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("link", { name: "Add your login" }));
  await screen.findByRole("heading", { name: "Connect to prod" });
  return user;
}

async function enterLogin(user: ReturnType<typeof userEvent.setup>) {
  await user.clear(screen.getByLabelText("Username"));
  await user.type(screen.getByLabelText("Username"), "demo");
  await user.type(screen.getByLabelText("Password"), TEST_PASSWORD);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Your login for a datasource", () => {
  it("checks the login, saves it and returns to the thread", async () => {
    const api = renderPage();
    const user = await openFromThread();
    expect(screen.queryByLabelText(/Role/)).not.toBeInTheDocument();

    await enterLogin(user);
    await user.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText("Issue thread")).toBeInTheDocument();
    const login = {
      username: "demo",
      password: TEST_PASSWORD,
      role: null,
      warehouse: null,
    };
    // Tested before it's saved, so a typo never gets stored
    expect(
      api.requests
        .filter((r) => r.method === "POST")
        .map((r) => [r.path, r.body]),
    ).toEqual([
      [`${CREDENTIALS}/test`, login],
      [CREDENTIALS, login],
    ]);
    expect(toast.success).toHaveBeenCalledWith(
      "Connected to prod as demo",
      expect.anything(),
    );
  });

  it("keeps a login the database refuses unsaved, and says why", async () => {
    const api = renderPage({
      test: {
        body: {
          success: false,
          error: 'password authentication failed for user "demo"',
        },
      },
    });
    const user = await openFromThread();

    await enterLogin(user);
    await user.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      'Couldn\'t connect with this login: password authentication failed for user "demo"',
    );
    expect(api.find("POST", CREDENTIALS)).toHaveLength(0);
    expect(screen.getByLabelText("Password")).toHaveValue(TEST_PASSWORD);
  });

  it("shows the saved login without its password, and removes it", async () => {
    const api = renderPage({
      status: { body: { configured: true, db_username: "demo" } },
    });
    const user = await openFromThread();

    expect(screen.getByText(/You're connected as/)).toHaveTextContent(
      "You're connected as demo. Enter a login to replace it.",
    );
    expect(screen.getByLabelText("Username")).toHaveValue("demo");
    expect(screen.getByLabelText("Password")).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Remove my login" }));

    await waitFor(() =>
      expect(api.find("DELETE", CREDENTIALS)).toHaveLength(1),
    );
    expect(toast.success).toHaveBeenCalledWith("Removed your login for prod");
  });

  it("asks for a role and warehouse where the source takes them", async () => {
    renderPage({ type: "snowflake" });
    await openFromThread();

    expect(screen.getByLabelText("Role (optional)")).toBeInTheDocument();
    expect(screen.getByLabelText("Warehouse (optional)")).toBeInTheDocument();
  });

  it("says when a source has no login to add", async () => {
    renderPage({ type: "local_file" });
    await openFromThread();

    expect(screen.getByText(/prod has no database login/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
  });

  it("goes back to the datasources when it was opened directly", async () => {
    renderPage({ route: PAGE });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Back" }));

    expect(await screen.findByText("Datasources")).toBeInTheDocument();
  });
});
