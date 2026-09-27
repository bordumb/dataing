import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { DatasetDetailPage } from "./dataset-detail-page";

vi.mock("@/lib/api/datasets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/datasets")>()),
  useDataset: () => ({
    data: {
      id: "ds-1",
      name: "orders",
      native_path: "analytics.orders",
      datasource_id: "src-1",
      datasource_name: "warehouse",
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
    data: { investigations: [] },
    isLoading: false,
  }),
}));

vi.mock("@/lib/api/schema-comments", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/schema-comments")>()),
  useSchemaComments: () => ({ data: [] }),
}));

async function openInvestigationsTab(role: OrgRole) {
  renderAsRole(
    <Routes>
      <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
    </Routes>,
    role,
    "/datasets/ds-1",
  );
  await userEvent.click(
    await screen.findByRole("tab", { name: /investigations/i }),
  );
  expect(await screen.findByText("No investigations")).toBeInTheDocument();
}

afterEach(() => localStorage.clear());

describe("DatasetDetailPage investigations tab", () => {
  it("does not offer viewers a way to start an investigation", async () => {
    await openInvestigationsTab("viewer");

    expect(screen.queryByText("Start Investigation")).not.toBeInTheDocument();
  });

  it("offers members a way to start an investigation", async () => {
    await openInvestigationsTab("member");

    expect(screen.getByText("Start Investigation")).toBeInTheDocument();
  });
});
