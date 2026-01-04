"use client";

import { useEffect, useState } from "react";
import {
  getDataset,
  getDatasetAnomalies,
  getDatasetInvestigations,
  getDatasetLineage,
} from "@/lib/api/datasets";
import type { Dataset, DatasetAnomaly, DatasetLineage } from "@/types/dataset";
import type { Investigation } from "@/types/investigation";

export function useDataset(datasetId: string) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [lineage, setLineage] = useState<DatasetLineage | null>(null);
  const [anomalies, setAnomalies] = useState<DatasetAnomaly[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      getDataset(datasetId),
      getDatasetLineage(datasetId),
      getDatasetAnomalies(datasetId),
      getDatasetInvestigations(datasetId, { limit: 5 }),
    ])
      .then(([datasetData, lineageData, anomalyData, investigationData]) => {
        if (!active) return;
        setDataset(datasetData);
        setLineage(lineageData);
        setAnomalies(anomalyData.anomalies);
        setInvestigations(investigationData);
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
  }, [datasetId]);

  return { dataset, lineage, anomalies, investigations, loading, error };
}
