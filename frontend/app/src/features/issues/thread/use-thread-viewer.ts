/**
 * Who is looking at a thread: their id, role and how to name people.
 */

import { useUserDirectory } from "@/lib/api/users";
import { useJwtAuth } from "@/lib/auth/jwt-context";
import { useRole } from "@/lib/auth/use-role";

import type { ThreadViewer } from "./ThreadMessageItem";

export function useThreadViewer(): ThreadViewer {
  const { user } = useJwtAuth();
  const { isMember, isAdmin } = useRole();
  const { nameOf } = useUserDirectory();
  return {
    userId: user?.id ?? null,
    isAdmin,
    canWrite: isMember,
    nameOf: (id) =>
      id && id === user?.id && user.name ? user.name : nameOf(id),
  };
}
