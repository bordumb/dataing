"use client";

import { useCallback, useEffect, useState } from "react";
import { useDebounce } from "@/lib/hooks/useDebounce";
import { searchDatasets, type DatasetSearchResult } from "@/lib/api/datasets";
import type { DatasetSource } from "@/components/investigations/dataset-types";

interface UseDatasetSearchOptions {
  source: DatasetSource;
  minQueryLength?: number;
  debounceMs?: number;
}

export function useDatasetSearch(options: UseDatasetSearchOptions) {
  const { source, minQueryLength = 2, debounceMs = 300 } = options;

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DatasetSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedQuery = useDebounce(query, debounceMs);

  useEffect(() => {
    if (debouncedQuery.length < minQueryLength) {
      setResults([]);
      setError(null);
      return;
    }

    let cancelled = false;

    const fetchResults = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const data = await searchDatasets({
          query: debouncedQuery,
          source,
          limit: 20,
        });

        if (!cancelled) {
          setResults(data.datasets);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Search failed");
          setResults([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchResults();

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, source, minQueryLength]);

  return {
    query,
    setQuery,
    results,
    isLoading,
    error,
    clearResults: useCallback(() => setResults([]), []),
  };
}
