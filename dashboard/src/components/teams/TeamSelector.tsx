"use client";

import { ChevronDown } from "lucide-react";
import { useTeamStore } from "@/lib/stores/team-store";
import type { Team } from "@/types/team";

interface TeamSelectorProps {
  initialTeam?: Team;
  availableTeams?: Team[];
}

export function TeamSelector({ initialTeam, availableTeams }: TeamSelectorProps) {
  // Pass real teams fetched from API, not mock data
  const storeTeams = useTeamStore((state) => state.teams);
  const currentTeamId = useTeamStore((state) => state.currentTeamId);
  const setCurrentTeam = useTeamStore((state) => state.setCurrentTeam);

  // Use provided teams from server (availableTeams) or fallback to store
  const teams = availableTeams && availableTeams.length > 0 ? availableTeams : storeTeams;
  const active = initialTeam ?? teams.find((team) => team.id === currentTeamId) ?? teams[0];

  return (
    <div className="relative flex w-full items-center justify-between rounded-xl border border-border bg-background-elevated/90 px-3 py-2 text-left">
      <div>
        <p className="text-xs uppercase tracking-widest text-foreground-muted">Team</p>
        <p className="text-sm font-semibold text-foreground">{active?.name ?? "Select team"}</p>
      </div>
      <ChevronDown className="h-4 w-4 text-foreground-muted" />
      <select
        value={active?.id ?? ""}
        onChange={(event) => setCurrentTeam(event.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {team.name}
          </option>
        ))}
      </select>
    </div>
  );
}
