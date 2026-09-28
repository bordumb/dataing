import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { stubApi, stubRadixDom } from "@/test/api";
import { renderAsRole } from "@/test/auth";
import { DatasetDetailPage } from "./dataset-detail-page";

const runs = vi.hoisted(() => ({ current: [] as Record<string, unknown>[] }));

vi.mock("@/lib/api/datasets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/datasets")>()),
  useDataset: () => ({
    data: {
      id: "ds-1",
      name: "orders",
      native_path: "analytics.orders",
      datasource_id: "src-2",
      datasource_name: "lake",
      datasource_type: "postgresql",
      table_type: "table",
      row_count: 10,
      column_count: 0,
      last_synced_at: null,
      columns: [],
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useDatasetInvestigations: () => ({
    data: { investigations: runs.current },
    isLoading: false,
  }),
}));

vi.mock("@/lib/api/schema-comments", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/schema-comments")>()),
  useSchemaComments: () => ({ data: [] }),
}));

function datasource(id: string, name: string) {
  return {
    id,
    name,
    type: "postgres",
    category: "database",
    is_active: true,
    is_default: false,
    status: "connected",
    created_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage(role: OrgRole) {
  stubApi({
    "GET /api/v1/datasources": {
      body: {
        items: [datasource("src-1", "warehouse"), datasource("src-2", "lake")],
        total: 2,
      },
    },
  });
  renderAsRole(
    <Routes>
      <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
    </Routes>,
    role,
    "/datasets/ds-1",
  );
}

beforeAll(() => stubRadixDom());

afterEach(() => {
  runs.current = [];
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("DatasetDetailPage", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    renderPage("viewer");

    expect(
      await screen.findByRole("heading", { name: "analytics.orders" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Investigate this dataset" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /investigations/i }));
    expect(await screen.findByText("No investigations")).toBeInTheDocument();
    expect(screen.queryByText(/Investigate/)).not.toBeInTheDocument();
  });

  it("investigates the dataset, pre-filled with its table and datasource", async () => {
    renderPage("member");

    await userEvent.click(
      await screen.findByRole("button", { name: "Investigate this dataset" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Start an investigation",
    });
    expect(within(dialog).getByLabelText("Scope: tables")).toHaveValue(
      "analytics.orders",
    );
    await within(dialog).findByRole("option", { name: /lake/ });
    expect(within(dialog).getByLabelText("Datasource")).toHaveValue("src-2");
  });

  it("offers it whether or not the dataset has runs", async () => {
    runs.current = [
      {
        id: "inv-1",
        metric_name: "null_rate",
        status: "completed",
        severity: null,
        created_at: "2026-09-14T08:00:00Z",
      },
    ];
    renderPage("member");

    expect(
      await screen.findByRole("button", { name: "Investigate this dataset" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /investigations/i }));
    expect(await screen.findByText("null_rate")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Investigate this dataset" }),
    ).toHaveLength(1);
  });
});
