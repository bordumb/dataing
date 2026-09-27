/**
 * Test helpers for rendering UI as a signed-in user with an org role.
 */

import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { JwtAuthProvider, RequireJwtAuth } from "@/lib/auth/jwt-context";
import type { Organization, OrgRole, User } from "@/lib/auth/types";

const ORG: Organization = {
  id: "org-1",
  name: "Acme",
  slug: "acme",
  plan: "pro",
};

function base64Url(value: object): string {
  return btoa(JSON.stringify(value))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/**
 * Build an unsigned JWT the frontend can decode. Only the server verifies
 * signatures, so the UI never needs a real one.
 */
export function fakeAccessToken(
  role: OrgRole,
  expiresInSeconds = 3600,
): string {
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: "user-1",
    org_id: ORG.id,
    role,
    teams: [],
    iat: now,
    exp: now + expiresInSeconds,
  };
  return `${base64Url({ alg: "HS256", typ: "JWT" })}.${base64Url(payload)}.signature`;
}

/**
 * Store a session the way JwtAuthProvider saves one after login.
 */
export function storeSession(
  role: OrgRole,
  accessToken: string = fakeAccessToken(role),
): void {
  const user: User = {
    id: "user-1",
    email: "user@acme.test",
    name: "Ada",
    org_id: ORG.id,
    role,
    created_at: "2026-01-01T00:00:00Z",
  };
  localStorage.clear();
  localStorage.setItem("dataing_access_token", accessToken);
  localStorage.setItem("dataing_refresh_token", "refresh-token");
  localStorage.setItem("dataing_user", JSON.stringify(user));
  localStorage.setItem("dataing_org", JSON.stringify(ORG));
  localStorage.setItem("dataing_role", role);
}

/**
 * Render UI behind the app's auth gate as a user holding `role`.
 *
 * Children render only once the session has loaded, so asserting that a
 * control is absent is meaningful as soon as any page content is on screen.
 */
export function renderAsRole(ui: ReactElement, role: OrgRole, route = "/") {
  storeSession(role);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <JwtAuthProvider>
          <RequireJwtAuth>{ui}</RequireJwtAuth>
        </JwtAuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
