import { useState, useEffect, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Loader2, X, Plus, AlertCircle } from "lucide-react";
import { useCreateIssue, useInvalidateIssues } from "@/lib/api/issues";
import type {
  IssueContext,
  IssueCreate as IssueCreateType,
} from "@/lib/api/issues";
import { useDataSources, SchemaTable } from "@/lib/api/datasources";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/Badge";
import {
  DatePicker,
  DatePickerValue,
  datePickerValueToString,
  stringToDatePickerValue,
} from "@/components/ui/DatePicker";
import {
  DatasetEntry,
  SchemaViewer,
} from "@/features/investigation/components";

interface Dataset {
  id: string;
  datasourceId: string;
  identifier: string;
}

interface FormData {
  title: string;
  description: string;
  priority: string;
  severity: string;
  column_name: string;
  labels: string[];
}

/** Today in the person's time zone; toISOString() gives the UTC day, which is
 * yesterday or tomorrow around midnight. */
function localToday(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function IssueCreate() {
  const navigate = useNavigate();
  const createIssue = useCreateIssue();
  const invalidate = useInvalidateIssues();
  const [labelInput, setLabelInput] = useState("");
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);

  const [datasets, setDatasets] = useState<Dataset[]>([
    { id: crypto.randomUUID(), datasourceId: "", identifier: "" },
  ]);

  const [issueDate, setIssueDate] = useState<DatePickerValue>(() =>
    stringToDatePickerValue(localToday()),
  );

  const [formData, setFormData] = useState<FormData>({
    title: "",
    description: "",
    priority: "",
    severity: "",
    column_name: "",
    labels: [],
  });

  const {
    data: dataSources,
    isLoading: isLoadingDataSources,
    error: dataSourcesError,
  } = useDataSources();

  // Auto-select first datasource
  useEffect(() => {
    if (dataSources && dataSources.length > 0 && !datasets[0].datasourceId) {
      setDatasets((prev) =>
        prev.map((ds, i) =>
          i === 0 ? { ...ds, datasourceId: dataSources[0].id } : ds,
        ),
      );
    }
  }, [dataSources, datasets]);

  const updateDataset = useCallback(
    (
      id: string,
      updates: Partial<{ datasourceId: string; identifier: string }>,
    ) => {
      setDatasets((prev) =>
        prev.map((ds) => (ds.id === id ? { ...ds, ...updates } : ds)),
      );
      if (updates.identifier === "" || updates.datasourceId) {
        setSelectedTable(null);
      }
    },
    [],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const primaryDataset = datasets[0];
    if (!formData.title.trim() || !primaryDataset.identifier.trim()) return;

    const context: IssueContext = {};
    const observedAt = datePickerValueToString(issueDate);
    if (observedAt) context.observed_at = observedAt;
    if (formData.column_name.trim()) {
      context.column = formData.column_name.trim();
    }

    try {
      const payload: IssueCreateType = {
        title: formData.title.trim(),
        description: formData.description.trim() || undefined,
        priority: formData.priority || undefined,
        severity: formData.severity || undefined,
        dataset_id: primaryDataset.identifier,
        labels: formData.labels.length > 0 ? formData.labels : undefined,
        context,
      };

      const result = await createIssue.mutateAsync({ data: payload });
      invalidate.invalidateList();
      navigate(`/issues/${result.id}`);
    } catch {
      // Shown below the form from createIssue.error.
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSelectChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value === "none" ? "" : value }));
  };

  const handleAddLabel = () => {
    const label = labelInput.trim().toLowerCase();
    if (label && !formData.labels.includes(label)) {
      setFormData((prev) => ({ ...prev, labels: [...prev.labels, label] }));
      setLabelInput("");
    }
  };

  const handleRemoveLabel = (label: string) => {
    setFormData((prev) => ({
      ...prev,
      labels: prev.labels.filter((l) => l !== label),
    }));
  };

  const handleLabelKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddLabel();
    }
  };

  const primaryDataset = datasets[0];
  const isSubmitDisabled =
    createIssue.isPending ||
    !formData.title.trim() ||
    !primaryDataset.identifier.trim();

  if (isLoadingDataSources) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/issues">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-3xl font-semibold">Create Issue</h1>
      </div>

      {dataSourcesError && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <div>
            <p className="font-medium text-destructive">
              Failed to load data sources
            </p>
            <p className="text-sm text-muted-foreground">
              {dataSourcesError.message}. Please check your settings and try
              again.
            </p>
          </div>
          <Link to="/settings" className="ml-auto">
            <Button variant="outline" size="sm">
              Check Settings
            </Button>
          </Link>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Issue Details</CardTitle>
              <p className="text-sm text-muted-foreground">
                Create a new issue to track data quality problems.
              </p>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label className="mb-1.5 block text-sm font-medium">
                    Title <span className="text-destructive">*</span>
                  </label>
                  <Input
                    id="title"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    placeholder="Brief description of the issue"
                    disabled={createIssue.isPending}
                  />
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-medium">
                    Dataset <span className="text-destructive">*</span>
                  </label>
                  <DatasetEntry
                    datasourceId={primaryDataset.datasourceId}
                    datasourceType={
                      dataSources?.find(
                        (d) => d.id === primaryDataset.datasourceId,
                      )?.type || "postgresql"
                    }
                    identifier={primaryDataset.identifier}
                    onDatasourceChange={(id) =>
                      updateDataset(primaryDataset.id, { datasourceId: id })
                    }
                    onIdentifierChange={(val) =>
                      updateDataset(primaryDataset.id, { identifier: val })
                    }
                    onRemove={() => {}}
                    canRemove={false}
                    disabled={createIssue.isPending}
                    dataSources={dataSources || []}
                    onTableSelect={setSelectedTable}
                  />
                  <p className="text-xs text-muted-foreground">
                    Select the dataset affected by this issue. Required for
                    spawning investigations.
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Issue Date
                    </label>
                    <DatePicker value={issueDate} onChange={setIssueDate} />
                    <p className="mt-1 text-xs text-muted-foreground">
                      When was the issue first observed?
                    </p>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Column Name
                    </label>
                    <Input
                      id="column_name"
                      name="column_name"
                      value={formData.column_name}
                      onChange={handleChange}
                      placeholder="e.g., user_id"
                      disabled={createIssue.isPending}
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      The specific column affected (optional)
                    </p>
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium">
                    Description
                  </label>
                  <Textarea
                    id="description"
                    name="description"
                    value={formData.description}
                    onChange={handleChange}
                    placeholder="Detailed description, context, and any relevant information..."
                    disabled={createIssue.isPending}
                    rows={4}
                  />
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Priority
                    </label>
                    <Select
                      value={formData.priority || "none"}
                      onValueChange={(v) => handleSelectChange("priority", v)}
                      disabled={createIssue.isPending}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select priority" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No priority</SelectItem>
                        <SelectItem value="P0">P0 - Critical</SelectItem>
                        <SelectItem value="P1">P1 - High</SelectItem>
                        <SelectItem value="P2">P2 - Medium</SelectItem>
                        <SelectItem value="P3">P3 - Low</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Severity
                    </label>
                    <Select
                      value={formData.severity || "none"}
                      onValueChange={(v) => handleSelectChange("severity", v)}
                      disabled={createIssue.isPending}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select severity" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No severity</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="low">Low</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium">
                    Labels
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={labelInput}
                      onChange={(e) => setLabelInput(e.target.value)}
                      onKeyDown={handleLabelKeyDown}
                      placeholder="Add a label..."
                      disabled={createIssue.isPending}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={handleAddLabel}
                      disabled={createIssue.isPending || !labelInput.trim()}
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {formData.labels.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {formData.labels.map((label) => (
                        <Badge
                          key={label}
                          variant="secondary"
                          className="gap-1"
                        >
                          {label}
                          <button
                            type="button"
                            onClick={() => handleRemoveLabel(label)}
                            className="hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                {createIssue.error && (
                  <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                    <p className="font-medium">Error creating issue:</p>
                    <p>{createIssue.error.message}</p>
                  </div>
                )}

                <div className="flex justify-end gap-3 border-t border-border pt-4">
                  <Link to="/issues">
                    <Button
                      variant="secondary"
                      disabled={createIssue.isPending}
                    >
                      Cancel
                    </Button>
                  </Link>
                  <Button type="submit" disabled={isSubmitDisabled}>
                    {createIssue.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      "Create Issue"
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-6 space-y-4">
            <h2 className="text-sm font-semibold">Dataset Preview</h2>
            <SchemaViewer table={selectedTable} isLoading={false} />

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Tips</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground space-y-3">
                <p>
                  <strong>Title:</strong> Be specific and concise. Good: "NULL
                  values in user_id column since Jan 15"
                </p>
                <p>
                  <strong>Dataset:</strong> Select the table or dataset where
                  the issue was observed.
                </p>
                <p>
                  <strong>Priority:</strong> P0/P1 for production-impacting
                  issues, P2/P3 for non-urgent improvements.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
