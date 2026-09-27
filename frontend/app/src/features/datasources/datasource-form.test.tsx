import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import type {
  ConfigSchema,
  SourceTypeResponse,
  TestConnectionResponse,
} from "@/lib/api/model";
import { queryKeys } from "@/lib/api/query-keys";
import { DataSourceForm } from "./datasource-form";

// Trimmed-down adapter schemas in the shape GET /api/v1/datasources/types
// serves them.
const SNOWFLAKE: ConfigSchema = {
  field_groups: [
    { id: "connection", label: "Connection", collapsed_by_default: false },
    { id: "auth", label: "Authentication", collapsed_by_default: false },
    { id: "advanced", label: "Advanced", collapsed_by_default: true },
  ],
  fields: [
    {
      name: "account",
      label: "Account",
      type: "string",
      required: true,
      group: "connection",
      placeholder: "xy12345.us-east-1",
      description: "Snowflake account identifier (e.g., xy12345.us-east-1)",
    },
    {
      name: "warehouse",
      label: "Warehouse",
      type: "string",
      required: true,
      group: "connection",
      placeholder: "COMPUTE_WH",
    },
    {
      name: "database",
      label: "Database",
      type: "string",
      required: true,
      group: "connection",
    },
    {
      name: "schema",
      label: "Schema",
      type: "string",
      required: false,
      group: "connection",
      default_value: "PUBLIC",
    },
    {
      name: "username",
      label: "Username",
      type: "string",
      required: true,
      group: "auth",
    },
    {
      name: "password",
      label: "Password",
      type: "secret",
      required: true,
      group: "auth",
    },
    {
      name: "role",
      label: "Role",
      type: "string",
      required: false,
      group: "advanced",
      placeholder: "ACCOUNTADMIN",
    },
    {
      name: "login_timeout",
      label: "Login Timeout (seconds)",
      type: "integer",
      required: false,
      group: "advanced",
      default_value: 60,
      min_value: 10,
      max_value: 300,
    },
  ],
};

const TRINO: ConfigSchema = {
  field_groups: [
    { id: "connection", label: "Connection", collapsed_by_default: false },
    { id: "auth", label: "Authentication", collapsed_by_default: false },
    { id: "advanced", label: "Advanced", collapsed_by_default: true },
  ],
  fields: [
    {
      name: "host",
      label: "Host",
      type: "string",
      required: true,
      group: "connection",
    },
    {
      name: "port",
      label: "Port",
      type: "integer",
      required: true,
      group: "connection",
      default_value: 8080,
      min_value: 1,
      max_value: 65535,
    },
    {
      name: "catalog",
      label: "Catalog",
      type: "string",
      required: true,
      group: "connection",
    },
    {
      name: "username",
      label: "Username",
      type: "string",
      required: true,
      group: "auth",
    },
    {
      name: "password",
      label: "Password",
      type: "secret",
      required: false,
      group: "auth",
    },
    {
      name: "http_scheme",
      label: "HTTP Scheme",
      type: "enum",
      required: false,
      group: "advanced",
      default_value: "http",
      options: [
        { value: "http", label: "HTTP" },
        { value: "https", label: "HTTPS" },
      ],
    },
    {
      name: "verify",
      label: "Verify SSL",
      type: "boolean",
      required: false,
      group: "advanced",
      default_value: true,
    },
  ],
};

const HDFS: ConfigSchema = {
  field_groups: [
    { id: "connection", label: "HDFS Connection", collapsed_by_default: false },
    { id: "auth", label: "Authentication", collapsed_by_default: true },
  ],
  fields: [
    {
      name: "namenode_host",
      label: "NameNode Host",
      type: "string",
      required: true,
      group: "connection",
    },
    {
      name: "kerberos_enabled",
      label: "Kerberos Authentication",
      type: "boolean",
      required: false,
      group: "auth",
      default_value: false,
    },
    {
      name: "kerberos_principal",
      label: "Kerberos Principal",
      type: "string",
      required: false,
      group: "auth",
      show_if: { field: "kerberos_enabled", value: true },
    },
  ],
};

function sourceType(
  type: string,
  display_name: string,
  config_schema: ConfigSchema,
): SourceTypeResponse {
  return {
    type,
    display_name,
    config_schema,
    category: "database",
    icon: type,
    description: "",
    capabilities: {},
  };
}

const SOURCE_TYPES = [
  sourceType("snowflake", "Snowflake", SNOWFLAKE),
  sourceType("trino", "Trino", TRINO),
  sourceType("hdfs", "HDFS", HDFS),
];

interface RecordedRequest {
  method: string;
  url: string;
  body: unknown;
}

const server = {
  requests: [] as RecordedRequest[],
  typesStatus: 200,
  connectionStatus: 200,
  connectionResult: { success: true, message: "Connected" } as unknown,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function fakeFetch(url: string, init: RequestInit = {}) {
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : undefined;
  server.requests.push({ method, url, body });

  if (method === "GET" && url === "/api/v1/datasources/types") {
    return server.typesStatus === 200
      ? jsonResponse({ types: SOURCE_TYPES })
      : jsonResponse({ detail: "Service unavailable" }, server.typesStatus);
  }
  if (method === "POST" && url === "/api/v1/datasources/test") {
    return jsonResponse(server.connectionResult, server.connectionStatus);
  }
  if (method === "POST" && url === "/api/v1/datasources") {
    return jsonResponse({ id: "ds-1" }, 201);
  }
  return jsonResponse({ detail: "Not found" }, 404);
}

function created(): unknown[] {
  return server.requests
    .filter((r) => r.method === "POST" && r.url === "/api/v1/datasources")
    .map((r) => r.body);
}

beforeAll(() => {
  // Radix primitives call browser APIs that jsdom does not implement.
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

beforeEach(() => {
  server.requests = [];
  server.typesStatus = 200;
  server.connectionStatus = 200;
  server.connectionResult = { success: true, message: "Connected" };
  vi.stubGlobal("fetch", vi.fn(fakeFetch));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

let queryClient: QueryClient;

function renderForm() {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <DataSourceForm open onOpenChange={() => undefined} />
      <Toaster />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

type User = ReturnType<typeof userEvent.setup>;

async function chooseType(user: User, displayName: string) {
  await user.click(await screen.findByRole("combobox", { name: "Type" }));
  await user.click(await screen.findByRole("option", { name: displayName }));
}

// Pasting keeps each field to one change event; typing re-renders per key.
async function fill(user: User, label: RegExp, text: string) {
  await user.click(await screen.findByLabelText(label));
  await user.paste(text);
}

async function fillSnowflakeLogin(user: User) {
  await fill(user, /^Account/, "xy12345.us-east-1");
  await fill(user, /^Warehouse/, "COMPUTE_WH");
  await fill(user, /^Database/, "ANALYTICS");
  await fill(user, /^Username/, "analyst");
  await fill(user, /^Password/, "not-a-real-password"); // pragma: allowlist secret
}

describe("DataSourceForm", () => {
  it("offers the source types the backend lists", async () => {
    const user = renderForm();

    await user.click(await screen.findByRole("combobox", { name: "Type" }));

    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "Snowflake",
      "Trino",
      "HDFS",
    ]);
  });

  it("says so when the source types cannot be loaded, and retries", async () => {
    server.typesStatus = 503;
    const user = renderForm();

    expect(
      await screen.findByText(/couldn't load data source types/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Type" })).toBeDisabled();

    server.typesStatus = 200;
    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Type" })).toBeEnabled(),
    );
    expect(screen.queryByText(/couldn't load/i)).not.toBeInTheDocument();
  });

  it("keeps the loaded types when a background refresh fails", async () => {
    renderForm();
    const type = await screen.findByRole("combobox", { name: "Type" });
    await waitFor(() => expect(type).toBeEnabled());

    server.typesStatus = 503;
    await act(async () => {
      await queryClient.refetchQueries();
      // React Query hands results to components on a zero-delay timer.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(queryClient.getQueryState(queryKeys.datasources.types)?.status).toBe(
      "error",
    );
    expect(type).toBeEnabled();
    expect(screen.queryByText(/couldn't load/i)).not.toBeInTheDocument();
  });

  it("renders the chosen adapter's fields in their backend groups", async () => {
    const user = renderForm();

    await chooseType(user, "Snowflake");

    expect(screen.getByLabelText(/^Account/)).toHaveAttribute(
      "placeholder",
      "xy12345.us-east-1",
    );
    expect(screen.getByLabelText(/^Schema/)).toHaveValue("PUBLIC");
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute(
      "type",
      "password",
    );
    expect(screen.getByRole("button", { name: "Connection" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    const advanced = screen.getByRole("button", { name: "Advanced" });
    expect(advanced).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText(/^Login Timeout/)).not.toBeInTheDocument();

    await user.click(advanced);

    expect(screen.getByLabelText(/^Login Timeout/)).toHaveValue(60);
    expect(screen.getByLabelText(/^Role/)).toHaveValue("");
  });

  it("submits the config under the backend's field names", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "Warehouse");
    await chooseType(user, "Snowflake");
    await fillSnowflakeLogin(user);
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(created()).toHaveLength(1));
    expect(created()[0]).toEqual({
      name: "Warehouse",
      type: "snowflake",
      config: {
        account: "xy12345.us-east-1",
        warehouse: "COMPUTE_WH",
        database: "ANALYTICS",
        schema: "PUBLIC",
        username: "analyst",
        password: "not-a-real-password", // pragma: allowlist secret
        login_timeout: 60,
      },
    });
  });

  it("submits the name without surrounding whitespace", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "  Warehouse  ");
    await chooseType(user, "Snowflake");
    await fillSnowflakeLogin(user);
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(created()).toHaveLength(1));
    expect(created()[0]).toMatchObject({ name: "Warehouse" });
  });

  it("maps enum and boolean fields onto a select and a checkbox", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "Lakehouse");
    await chooseType(user, "Trino");
    await fill(user, /^Host/, "trino.internal");
    await fill(user, /^Catalog/, "hive");
    await fill(user, /^Username/, "analyst");
    await user.click(screen.getByRole("button", { name: "Advanced" }));

    const scheme = screen.getByRole("combobox", { name: "HTTP Scheme" });
    const verify = screen.getByRole("checkbox", { name: "Verify SSL" });
    expect(scheme).toHaveTextContent("HTTP");
    expect(verify).toBeChecked();

    await user.click(scheme);
    await user.click(await screen.findByRole("option", { name: "HTTPS" }));
    await user.click(verify);
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(created()).toHaveLength(1));
    expect(created()[0]).toMatchObject({
      type: "trino",
      config: {
        host: "trino.internal",
        port: 8080,
        catalog: "hive",
        username: "analyst",
        http_scheme: "https",
        verify: false,
      },
    });
  });

  it("validates against the schema before submitting", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "Warehouse");
    await chooseType(user, "Snowflake");
    await user.click(screen.getByRole("button", { name: "Advanced" }));
    const timeout = screen.getByLabelText(/^Login Timeout/);
    await user.clear(timeout);
    await user.type(timeout, "5");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("Account is required")).toBeInTheDocument();
    expect(
      screen.getByText("Login Timeout (seconds) must be at least 10"),
    ).toBeInTheDocument();
    expect(created()).toHaveLength(0);
  });

  it("opens a collapsed group to show its error and keeps it open", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "Warehouse");
    await chooseType(user, "Snowflake");
    await fillSnowflakeLogin(user);
    const advanced = screen.getByRole("button", { name: "Advanced" });
    await user.click(advanced);
    const timeout = screen.getByLabelText(/^Login Timeout/);
    await user.clear(timeout);
    await user.type(timeout, "5");
    await user.click(advanced);
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(
      await screen.findByText("Login Timeout (seconds) must be at least 10"),
    ).toBeInTheDocument();
    expect(advanced).toHaveAttribute("aria-expanded", "true");

    await user.type(screen.getByLabelText(/^Login Timeout/), "0");

    expect(screen.getByLabelText(/^Login Timeout/)).toHaveValue(50);
    expect(advanced).toHaveAttribute("aria-expanded", "true");
  });

  it("shows a conditional field only while its condition holds", async () => {
    const user = renderForm();

    await chooseType(user, "HDFS");
    await user.click(screen.getByRole("button", { name: "Authentication" }));

    expect(
      screen.queryByLabelText(/^Kerberos Principal/),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("checkbox", { name: "Kerberos Authentication" }),
    );

    expect(screen.getByLabelText(/^Kerberos Principal/)).toBeInTheDocument();
  });

  it("leaves a hidden conditional field out of the config", async () => {
    const user = renderForm();

    await fill(user, /^Name/, "Lake");
    await chooseType(user, "HDFS");
    await fill(user, /^NameNode Host/, "namenode.internal");
    await user.click(screen.getByRole("button", { name: "Authentication" }));
    const kerberos = screen.getByRole("checkbox", {
      name: "Kerberos Authentication",
    });
    await user.click(kerberos);
    await fill(user, /^Kerberos Principal/, "etl@EXAMPLE.COM");
    await user.click(kerberos);
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(created()).toHaveLength(1));
    expect(created()[0]).toMatchObject({
      config: { namenode_host: "namenode.internal", kerberos_enabled: false },
    });
    expect(created()[0]).not.toHaveProperty("config.kerberos_principal");
  });

  it("reports a failed connection test as a failure", async () => {
    server.connectionResult = {
      success: false,
      message: "Incorrect username or password was specified.",
    } satisfies TestConnectionResponse;
    const user = renderForm();

    await chooseType(user, "Snowflake");
    await fillSnowflakeLogin(user);
    await user.click(screen.getByRole("button", { name: "Test Connection" }));

    expect(
      await screen.findByText(/Incorrect username or password/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/connection successful/i),
    ).not.toBeInTheDocument();
  });

  it("reports why the backend refused a connection test", async () => {
    server.connectionStatus = 400;
    server.connectionResult = {
      detail: "Source type not available: snowflake",
    };
    const user = renderForm();

    await chooseType(user, "Snowflake");
    await fillSnowflakeLogin(user);
    await user.click(screen.getByRole("button", { name: "Test Connection" }));

    expect(
      await screen.findByText(
        "Connection failed: Source type not available: snowflake",
      ),
    ).toBeInTheDocument();
  });
});
