"use client";

import { useEffect, useState } from "react";
import { getTeam, getTeamDatasets, getTeamInvestigations, getTeamMembers, getTeamStats } from "@/lib/api/teams";
import type { Dataset } from "@/types/dataset";
import type { Investigation } from "@/types/investigation";
import type { Team, TeamMember, TeamStats } from "@/types/team";

export function useTeam(teamId: string) {
  const [team, setTeam] = useState<Team | null>(null);
  const [stats, setStats] = useState<TeamStats | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      getTeam(teamId),
      getTeamStats(teamId),
      getTeamDatasets(teamId),
      getTeamInvestigations(teamId, { limit: 10 }),
      getTeamMembers(teamId),
    ])
      .then(([teamData, statsData, datasetData, investigationData, memberData]) => {
        if (!active) return;
        setTeam(teamData);
        setStats(statsData);
        setDatasets(datasetData);
        setInvestigations(investigationData);
        setMembers(memberData);
        setError(null);
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [teamId]);

  return { team, stats, datasets, investigations, members, loading, error };
}
