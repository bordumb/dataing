import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardStatsCards } from "./dashboard-stats";

describe("DashboardStatsCards", () => {
  it("shows each stat", () => {
    render(
      <DashboardStatsCards
        stats={{ activeInvestigations: 4, completedToday: 1, dataSources: 2 }}
        isLoading={false}
        isError={false}
      />,
    );

    expect(screen.getByLabelText("Active Investigations")).toHaveTextContent(
      "4",
    );
    expect(screen.getByLabelText("Completed Today")).toHaveTextContent("1");
    expect(screen.getByLabelText("Data Sources")).toHaveTextContent("2");
  });

  it("shows no numbers when the stats failed to load", () => {
    render(
      <DashboardStatsCards
        stats={undefined}
        isLoading={false}
        isError={true}
      />,
    );

    for (const title of [
      "Active Investigations",
      "Completed Today",
      "Data Sources",
    ]) {
      expect(screen.getByLabelText(title)).toHaveTextContent("—");
    }
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Couldn't load dashboard stats.",
    );
  });
});
