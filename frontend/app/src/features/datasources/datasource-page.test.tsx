import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderAsRole } from "@/test/auth";
import { DataSourcePage } from "./datasource-page";

const datasources = vi.hoisted(() => ({ current: [] as unknown[] }));

vi.mock("@/lib/api/datasources", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/datasources")>()),
  useDataSources: () => ({
    data: datasources.current,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSourceTypes: () => ({ data: [] }),
}));

const warehouse = {
  id: "src-1",
  name: "warehouse",
  type: "postgresql",
  status: "healthy",
  last_synced_at: null,
  created_at: "2026-09-01T00:00:00Z",
};

afterEach(() => {
  localStorage.clear();
  datasources.current = [];
});

describe("DataSourcePage", () => {
  it("does not offer members a way to add a data source", async () => {
    renderAsRole(<DataSourcePage />, "member");

    expect(await screen.findByText("No data sources")).toBeInTheDocument();
    expect(screen.queryAllByText("Add Data Source")).toHaveLength(0);
  });

  it("offers admins a way to add a data source", async () => {
    renderAsRole(<DataSourcePage />, "admin");

    expect(await screen.findAllByText("Add Data Source")).toHaveLength(2);
  });

  it("does not offer members a way to delete a data source", async () => {
    datasources.current = [warehouse];
    renderAsRole(<DataSourcePage />, "member");

    await userEvent.click(
      await screen.findByRole("button", { name: "Open menu" }),
    );

    expect(await screen.findByText("Copy ID")).toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
  });

  it("offers admins a way to delete a data source", async () => {
    datasources.current = [warehouse];
    renderAsRole(<DataSourcePage />, "admin");

    await userEvent.click(
      await screen.findByRole("button", { name: "Open menu" }),
    );

    expect(await screen.findByText("Delete")).toBeInTheDocument();
  });
});
