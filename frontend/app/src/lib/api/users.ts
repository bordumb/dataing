/**
 * People in the caller's tenant, for showing names instead of user ids.
 */

import * as React from "react";

import { useListUsersApiV1UsersGet } from "./generated/users/users";
import type { UserResponse } from "./model";

export interface UserDirectory {
  users: UserResponse[];
  /** Display name for a user id: name, then email, then a short id. */
  nameOf: (userId: string | null | undefined) => string;
}

export function displayName(user: Pick<UserResponse, "name" | "email">) {
  return user.name || user.email;
}

export function useUserDirectory(): UserDirectory {
  const query = useListUsersApiV1UsersGet({
    query: { staleTime: 5 * 60 * 1000 },
  });
  const users = React.useMemo(() => query.data?.users ?? [], [query.data]);

  return React.useMemo(() => {
    const byId = new Map(users.map((u) => [u.id, u]));
    return {
      users,
      nameOf: (userId) => {
        if (!userId) return "Someone";
        const user = byId.get(userId);
        return user ? displayName(user) : `User ${userId.slice(0, 8)}`;
      },
    };
  }, [users]);
}
