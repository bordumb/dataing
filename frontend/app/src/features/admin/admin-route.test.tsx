import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { AdminRoute } from "./admin-route";

vi.mock("./admin-page", () => ({
  AdminPage: () => <p>Admin console</p>,
}));

function visitAdmin(role: OrgRole) {
  return renderAsRole(
    <Routes>
      <Route path="/" element={<p>Dashboard</p>} />
      <Route path="/admin" element={<AdminRoute />} />
    </Routes>,
    role,
    "/admin",
  );
}

afterEach(() => localStorage.clear());

describe("AdminRoute", () => {
  it.each(["viewer", "member"] as const)(
    "sends %s users who open /admin to the dashboard",
    async (role) => {
      visitAdmin(role);

      expect(await screen.findByText("Dashboard")).toBeInTheDocument();
      expect(screen.queryByText("Admin console")).not.toBeInTheDocument();
    },
  );

  it.each(["admin", "owner"] as const)(
    "lets %s users open /admin",
    async (role) => {
      visitAdmin(role);

      expect(await screen.findByText("Admin console")).toBeInTheDocument();
    },
  );
});
