import { create } from "zustand";
import { users } from "@/lib/api/mock-data";
import type { User, UserRole } from "@/types/user";

interface UserState {
  user: User | null;
  viewAsRole: UserRole | null;
  setUser: (user: User | null) => void;
  setViewAsRole: (role: UserRole | null) => void;
}

export const useUserStore = create<UserState>((set) => ({
  user: users[0] ?? null,
  viewAsRole: null,
  setUser: (user) => set({ user }),
  setViewAsRole: (role) => set({ viewAsRole: role }),
}));
