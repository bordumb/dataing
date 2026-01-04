"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import {
  DatePicker,
  createEmptyDatePickerValue,
  datePickerValueToAPI,
  type DatePickerValue,
} from "@/components/ui/DatePicker";
import { startInvestigation } from "@/lib/api/investigations";
import { getDatasetSchema } from "@/lib/api/datasets";
import { getTeams } from "@/lib/api/teams";
import { DatasetSelector } from "@/components/investigations/DatasetSelector";
import { SchemaViewer } from "@/components/datasets/SchemaViewer";
import {
  createEmptyDatasetSelection,
  type DatasetSelection,
} from "@/components/investigations/dataset-types";
import type { Team } from "@/types/team";
import type { DatasetSchema } from "@/types/dataset";

export default function NewInvestigationPage() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [datasets, setDatasets] = useState<DatasetSelection[]>([createEmptyDatasetSelection()]);
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [teamId, setTeamId] = useState("");
  const [teams, setTeams] = useState<Team[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schema, setSchema] = useState<DatasetSchema | null>(null);
  const [anomalyPeriod, setAnomalyPeriod] = useState<DatePickerValue>(createEmptyDatePickerValue());

  const hasEmptyDataset = datasets.some((dataset) => !dataset.identifier.trim());
  const hasNoAnomalyDate = !anomalyPeriod.start;
  const isSubmitDisabled = isSubmitting || hasEmptyDataset || hasNoAnomalyDate;
  const primaryDataset = datasets[0];

  // Fetch teams on mount
  useEffect(() => {
    getTeams().then(setTeams);
  }, []);

  // Fetch schema when primary dataset changes
  const fetchSchema = useCallback(async (identifier: string) => {
    if (!identifier.trim()) {
      setSchema(null);
      return;
    }
    setSchemaLoading(true);
    try {
      const result = await getDatasetSchema(identifier);
      setSchema(result);
    } catch (err) {
      console.error("Failed to fetch schema:", err);
      setSchema(null);
    } finally {
      setSchemaLoading(false);
    }
  }, []);

  // Debounced schema fetch when identifier changes
  useEffect(() => {
    const identifier = primaryDataset?.identifier?.trim();
    if (!identifier) {
      setSchema(null);
      return;
    }
    const timeout = setTimeout(() => fetchSchema(identifier), 500);
    return () => clearTimeout(timeout);
  }, [primaryDataset?.identifier, fetchSchema]);

  const handleDatasetsChange = (next: DatasetSelection[]) => {
    setDatasets(next);
    if (error) {
      setError(null);
    }
  };

  const handleSubmit = async () => {
    const normalizedDatasets = datasets.map((dataset) => ({
      ...dataset,
      identifier: dataset.identifier.trim(),
    }));

    if (!normalizedDatasets.length || normalizedDatasets.some((dataset) => !dataset.identifier)) {
      setError("All dataset identifiers are required");
      return;
    }

    if (!anomalyPeriod.start) {
      setError("Please select an anomaly date");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // Convert DatePickerValue to API format
      const anomalyPeriodAPI = datePickerValueToAPI(anomalyPeriod);

      const result = await startInvestigation({
        datasets: normalizedDatasets.map((dataset, index) => ({
          source: dataset.source,
          identifier: dataset.identifier,
          role: index === 0 ? "primary" : "secondary",
        })),
        description: description.trim() || "Manual investigation",
        priority,
        team_id: teamId || undefined,
        anomalyPeriod: anomalyPeriodAPI || undefined,
      });

      router.push(`/investigations/${result.investigation_id}`);
    } catch (err) {
      console.error("Failed to start investigation:", err);
      setError(err instanceof Error ? err.message : "Failed to start investigation");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/investigations">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <h1 className="section-title text-3xl font-semibold">Start Investigation</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Form */}
        <div className="lg:col-span-2">
          <Card
            title="Investigation Details"
            description="Configure the investigation parameters and target datasets."
          >
            <div className="space-y-5">
              <DatasetSelector
                datasets={datasets}
                onChange={handleDatasetsChange}
                disabled={isSubmitting}
              />

              {/* Anomaly Date - Critical for accurate investigation */}
              <DatePicker
                label="Anomaly Date"
                value={anomalyPeriod}
                onChange={setAnomalyPeriod}
                disabled={isSubmitting}
                required
                hint="When did the anomaly occur? Use 'Date Range' for trend analysis."
                error={hasNoAnomalyDate && error ? "Anomaly date is required" : undefined}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <Select
                  label="Priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  disabled={isSubmitting}
                >
                  <option value="low">Low - Background analysis</option>
                  <option value="medium">Medium - Standard priority</option>
                  <option value="high">High - Immediate attention</option>
                </Select>

                <Select
                  label="Assign to Team"
                  value={teamId}
                  onChange={(e) => setTeamId(e.target.value)}
                  disabled={isSubmitting}
                >
                  <option value="">No team assigned</option>
                  {teams.map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.name}
                    </option>
                  ))}
                </Select>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">
                  Description
                </label>
                <Textarea
                  rows={4}
                  placeholder="Describe the anomaly, expected behavior, or specific questions to investigate..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isSubmitting}
                />
                <p className="mt-1 text-xs text-foreground-muted">
                  Provide context to help the AI agent focus its investigation.
                </p>
              </div>

              {error && (
                <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 border-t border-border pt-4">
                <Link href="/investigations">
                  <Button variant="secondary" disabled={isSubmitting}>
                    Cancel
                  </Button>
                </Link>
                <Button onClick={handleSubmit} disabled={isSubmitDisabled}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Starting Investigation...
                    </>
                  ) : (
                    "Run Investigation"
                  )}
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Schema Preview Sidebar */}
        <div className="lg:col-span-1">
          <div className="sticky top-6 space-y-4">
            <h2 className="text-sm font-semibold text-foreground">Dataset Preview</h2>
            {schemaLoading ? (
              <div className="flex items-center justify-center rounded-xl border border-border bg-background-elevated/80 p-8">
                <Loader2 className="h-6 w-6 animate-spin text-foreground-muted" />
              </div>
            ) : schema ? (
              <SchemaViewer schema={schema} compact />
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-background-subtle/50 p-8 text-center">
                <p className="text-sm text-foreground-muted">
                  {primaryDataset?.identifier?.trim()
                    ? "Schema not available"
                    : "Enter a dataset identifier to preview its schema"}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
