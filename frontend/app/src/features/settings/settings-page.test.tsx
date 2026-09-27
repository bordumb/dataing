import { afterEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderAsRole } from "@/test/auth";
import { SettingsPage } from "./settings-page";

afterEach(() => localStorage.clear());

describe("SettingsPage", () => {
  it("does not show members the admin-only tabs", async () => {
    renderAsRole(<SettingsPage />, "member");

    expect(await screen.findByText("General")).toBeInTheDocument();
    expect(screen.getByText("Notifications")).toBeInTheDocument();
    expect(screen.queryByText("Webhooks")).not.toBeInTheDocument();
    expect(screen.queryByText("API Keys")).not.toBeInTheDocument();
  });

  it("shows admins the admin-only tabs", async () => {
    renderAsRole(<SettingsPage />, "admin");

    expect(await screen.findByText("Webhooks")).toBeInTheDocument();
    expect(screen.getByText("API Keys")).toBeInTheDocument();
  });
});
