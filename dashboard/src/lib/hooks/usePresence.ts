"use client";

import { useEffect, useState } from "react";
import { users } from "@/lib/api/mock-data";
import type { User } from "@/types/user";

export function usePresence(_investigationId: string) {
  const [viewers, setViewers] = useState<User[]>([]);

  useEffect(() => {
    setViewers(users.slice(0, 3));
  }, []);

  return { viewers };
}
