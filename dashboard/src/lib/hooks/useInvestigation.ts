"use client";

import { useEffect, useState } from "react";
import { getInvestigation, getRelatedInvestigations } from "@/lib/api/investigations";
import type { Investigation, RelatedInvestigations } from "@/types/investigation";

export function useInvestigation(id: string) {
  const [data, setData] = useState<Investigation | null>(null);
  const [related, setRelated] = useState<RelatedInvestigations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getInvestigation(id), getRelatedInvestigations(id)])
      .then(([investigation, relatedInvestigations]) => {
        if (!active) return;
        setData(investigation);
        setRelated(relatedInvestigations);
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
  }, [id]);

  return { data, related, loading, error };
}
