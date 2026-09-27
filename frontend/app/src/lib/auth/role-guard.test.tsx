import { afterEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import type { OrgRole } from "@/lib/auth/types";
import { renderAsRole } from "@/test/auth";
import { RoleGuard } from "./role-guard";

/** The shape App.tsx uses to keep create pages to members. */
function renderCreatePage(role: OrgRole) {
  return renderAsRole(
    <Routes>
      <Route path="/issues" element={<p>Issue list</p>} />
      <Route
        path="/issues/new"
        element={
          <RoleGuard minRole="member" redirectTo="/issues">
            <p>Create issue form</p>
          </RoleGuard>
        }
      />
    </Routes>,
    role,
    "/issues/new",
  );
}

afterEach(() => localStorage.clear());

describe("RoleGuard page redirect", () => {
  it("sends viewers who open a create page back to the list", async () => {
    renderCreatePage("viewer");

    expect(await screen.findByText("Issue list")).toBeInTheDocument();
    expect(screen.queryByText("Create issue form")).not.toBeInTheDocument();
  });

  it("lets members open a create page", async () => {
    renderCreatePage("member");

    expect(await screen.findByText("Create issue form")).toBeInTheDocument();
  });
});
