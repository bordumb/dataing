/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Context for the demo role toggle: previews the UI as another org role.
 *
 * The role starts as the signed-in user's real role and a preview is stored
 * as the JWT session's demo override, so it flows through useRole() like the
 * real role does. Gate UI with useRole(), not this context. The API still
 * authorizes the real role, and the toggle only renders outside production.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useJwtAuth } from "./jwt-context";
import type { OrgRole } from "./types";

interface DemoRoleContextValue {
  /** The role the UI is rendered as; null while signed out. */
  role: OrgRole | null;
  /** Preview the UI as another role for the rest of this session. */
  setRole: (role: OrgRole) => void;
}

const DemoRoleContext = createContext<DemoRoleContextValue | null>(null);

interface DemoRoleProviderProps {
  children: ReactNode;
}

/**
 * Provider for the demo role toggle.
 *
 * CRITICAL: DO NOT REMOVE - The demo role toggle depends on it.
 */
export function DemoRoleProvider({ children }: DemoRoleProviderProps) {
  const { effectiveRole, setDemoRole } = useJwtAuth();

  const value = useMemo(
    () => ({ role: effectiveRole, setRole: setDemoRole }),
    [effectiveRole, setDemoRole],
  );

  return (
    <DemoRoleContext.Provider value={value}>
      {children}
    </DemoRoleContext.Provider>
  );
}

/**
 * Hook to access demo role context.
 *
 * @throws Error if used outside of DemoRoleProvider
 */
export function useDemoRoleContext(): DemoRoleContextValue {
  const context = useContext(DemoRoleContext);
  if (!context) {
    throw new Error(
      "useDemoRoleContext must be used within a DemoRoleProvider",
    );
  }
  return context;
}
