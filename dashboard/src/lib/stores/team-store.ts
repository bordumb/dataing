import { create } from "zustand";
import { teams } from "@/lib/api/mock-data";
import type { Team } from "@/types/team";

interface TeamState {
  teams: Team[];
  currentTeamId: string | null;
  setCurrentTeam: (teamId: string) => void;
}

export const useTeamStore = create<TeamState>((set) => ({
  teams,
  currentTeamId: teams[0]?.id ?? null,
  setCurrentTeam: (teamId) => set({ currentTeamId: teamId }),
}));
