import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { stubApi } from "@/test/api";
import { renderAsRole } from "@/test/auth";

import { IssueCreate } from "./IssueCreate";

// The dataset picker loads schemas; a plain input stands in for it here.
vi.mock("@/features/investigation/components", () => ({
  DatasetEntry: ({
    identifier,
    onIdentifierChange,
  }: {
    identifier: string;
    onIdentifierChange: (value: string) => void;
  }) => (
    <input
      aria-label="Dataset"
      value={identifier}
      onChange={(e) => onIdentifierChange(e.target.value)}
    />
  ),
  SchemaViewer: () => null,
}));

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function today(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

describe("IssueCreate", () => {
  it("sends the observed date and column as the issue's context", async () => {
    const api = stubApi({
      "GET /api/v1/datasources": {
        body: {
          items: [{ id: "ds-1", name: "warehouse", type: "postgresql" }],
          total: 1,
        },
      },
      "POST /api/v1/issues": { status: 201, body: { id: "issue-9" } },
    });
    const user = userEvent.setup();
    renderAsRole(
      <Routes>
        <Route path="/issues/new" element={<IssueCreate />} />
        <Route path="/issues/:id" element={<p>Issue page</p>} />
      </Routes>,
      "member",
      "/issues/new",
    );

    await user.click(
      await screen.findByPlaceholderText("Brief description of the issue"),
    );
    await user.paste("Nulls in orders.email");
    await user.click(screen.getByLabelText("Dataset"));
    await user.paste("public.orders");
    await user.click(screen.getByPlaceholderText("e.g., user_id"));
    await user.paste("email");
    await user.click(screen.getByRole("button", { name: "Create Issue" }));

    expect(await screen.findByText("Issue page")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.find("POST", "/api/v1/issues")).toHaveLength(1),
    );
    expect(api.find("POST", "/api/v1/issues")[0].body).toMatchObject({
      title: "Nulls in orders.email",
      dataset_id: "public.orders",
      context: { observed_at: today(), column: "email" },
    });
  });
});
