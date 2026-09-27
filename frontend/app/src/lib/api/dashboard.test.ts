import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchDashboardStats } from "./dashboard";

function respondWith(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: status < 400,
    status,
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchDashboardStats", () => {
  it("reads the stats from GET /api/v1/dashboard/stats", async () => {
    const fetchMock = respondWith(200, {
      active_investigations: 4,
      completed_today: 1,
      data_sources: 2,
    });

    await expect(fetchDashboardStats()).resolves.toEqual({
      activeInvestigations: 4,
      completedToday: 1,
      dataSources: 2,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/dashboard\/stats$/),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("fails instead of inventing numbers when the API errors", async () => {
    respondWith(500, { detail: "database unavailable" });

    await expect(fetchDashboardStats()).rejects.toThrow("database unavailable");
  });
});
