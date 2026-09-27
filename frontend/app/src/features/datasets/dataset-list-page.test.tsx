import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderAsRole } from "@/test/auth";
import { DatasetListPage } from "./dataset-list-page";

vi.mock("@/lib/api/datasets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/datasets")>()),
  useDatasets: () => ({
    data: { datasets: [] },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSyncDatasource: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/lib/api/datasources", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/datasources")>()),
  useDataSource: () => ({ data: { name: "warehouse" } }),
}));

afterEach(() => localStorage.clear());

function renderPage(role: "viewer" | "member") {
  return renderAsRole(
    <Routes>
      <Route
        path="/datasources/:datasourceId/datasets"
        element={<DatasetListPage />}
      />
    </Routes>,
    role,
    "/datasources/ds-1/datasets",
  );
}

describe("DatasetListPage", () => {
  it("does not offer viewers a schema sync", async () => {
    renderPage("viewer");

    expect(await screen.findByText("No datasets found")).toBeInTheDocument();
    expect(screen.queryAllByText("Sync Schema")).toHaveLength(0);
  });

  it("offers members a schema sync", async () => {
    renderPage("member");

    expect(await screen.findAllByText("Sync Schema")).toHaveLength(2);
  });
});
