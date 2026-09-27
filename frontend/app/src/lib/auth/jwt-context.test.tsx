import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeAccessToken, storeSession } from "@/test/auth";
import * as authApi from "./api";
import { JwtAuthProvider, useJwtAuth } from "./jwt-context";
import { useRole } from "./use-role";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  refreshToken: vi.fn(),
}));

function SessionProbe() {
  const { role } = useRole();
  const { user } = useJwtAuth();
  return (
    <p>
      role:{role ?? "none"} user:{user?.email ?? "none"}
    </p>
  );
}

function DemoRoleProbe() {
  const { role } = useRole();
  const { setDemoRole, logout } = useJwtAuth();
  return (
    <div>
      <p>role:{role ?? "none"}</p>
      <button onClick={() => setDemoRole("admin")}>Preview as admin</button>
      <button onClick={logout}>Log out</button>
    </div>
  );
}

afterEach(() => {
  localStorage.clear();
  vi.mocked(authApi.refreshToken).mockReset();
});

describe("JwtAuthProvider session role", () => {
  it("takes the role from the access token, not from stored state", async () => {
    storeSession("admin", fakeAccessToken("viewer"));

    render(
      <JwtAuthProvider>
        <SessionProbe />
      </JwtAuthProvider>,
    );

    expect(await screen.findByText(/role:viewer/)).toBeInTheDocument();
  });

  it("restores the role and user after refreshing an expired session", async () => {
    storeSession("admin", fakeAccessToken("admin", -120));
    vi.mocked(authApi.refreshToken).mockResolvedValue({
      access_token: fakeAccessToken("viewer"),
      token_type: "bearer",
    });

    render(
      <JwtAuthProvider>
        <SessionProbe />
      </JwtAuthProvider>,
    );

    expect(
      await screen.findByText("role:viewer user:user@acme.test"),
    ).toBeInTheDocument();
  });
});

describe("JwtAuthProvider demo role preview", () => {
  it("is dropped on logout so it cannot carry into the next session", async () => {
    storeSession("viewer");
    render(
      <JwtAuthProvider>
        <DemoRoleProbe />
      </JwtAuthProvider>,
    );
    await userEvent.click(await screen.findByText("Preview as admin"));
    expect(await screen.findByText("role:admin")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Log out"));

    expect(await screen.findByText("role:none")).toBeInTheDocument();
  });
});
