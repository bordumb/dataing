import * as React from "react";
import {
  Plus,
  Trash2,
  Loader2,
  AlertTriangle,
  Database,
  Search,
  Table as TableIcon,
} from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/shared/empty-state";
import {
  useGetTeamPolicyApiV1TeamsTeamIdPolicyGet,
  useUpdateTeamPolicyApiV1TeamsTeamIdPolicyPut,
  useCreatePolicyOverrideApiV1TeamsTeamIdPolicyOverridesPost,
  useDeletePolicyOverrideApiV1TeamsTeamIdPolicyOverridesOverrideIdDelete,
  useUpdateQueueLimitsApiV1TeamsTeamIdPolicyQueueLimitsPut,
  getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey,
} from "@/lib/api/generated/teams/teams";
import type { TeamPolicyOverrideResponse } from "@/lib/api/model";
import { useDataSources, useTableSearch } from "@/lib/api/datasources";

const ALERT_SOURCES = [
  "monte_carlo",
  "great_expectations",
  "dbt",
  "pagerduty",
  "jira",
  "custom",
];
const POLICY_ACTIONS = ["auto", "review", "issue_only"];
const SEVERITY_LEVELS = ["low", "medium", "high", "critical"];

interface TeamPolicyEditorProps {
  teamId: string;
  teamName: string;
  onClose: () => void;
}

export function TeamPolicyEditor({
  teamId,
  teamName,
  onClose,
}: TeamPolicyEditorProps) {
  const queryClient = useQueryClient();
  const [showOverrideDialog, setShowOverrideDialog] = React.useState(false);
  const [newOverride, setNewOverride] = React.useState({
    datasourceId: "",
    datasetId: "",
    defaultAction: "",
    autoInvestigateMinSeverity: "",
    reviewRequiredMaxSeverity: "",
  });
  const [datasetSearchTerm, setDatasetSearchTerm] = React.useState("");
  const [isDatasetDropdownOpen, setIsDatasetDropdownOpen] =
    React.useState(false);
  const datasetInputRef = React.useRef<HTMLInputElement>(null);
  const datasetDropdownRef = React.useRef<HTMLDivElement>(null);

  // Fetch datasources for the picker
  const { data: dataSources } = useDataSources();

  // Search tables when typing in dataset field
  const { data: tables, isLoading: isLoadingTables } = useTableSearch(
    newOverride.datasourceId,
    datasetSearchTerm,
  );

  // Auto-select first datasource when dialog opens
  React.useEffect(() => {
    if (
      showOverrideDialog &&
      dataSources &&
      dataSources.length > 0 &&
      !newOverride.datasourceId
    ) {
      setNewOverride((prev) => ({ ...prev, datasourceId: dataSources[0].id }));
    }
  }, [showOverrideDialog, dataSources, newOverride.datasourceId]);

  // Debounce search term
  React.useEffect(() => {
    const timer = setTimeout(
      () => setDatasetSearchTerm(newOverride.datasetId),
      300,
    );
    return () => clearTimeout(timer);
  }, [newOverride.datasetId]);

  // Close dropdown on outside click
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        datasetDropdownRef.current &&
        !datasetDropdownRef.current.contains(event.target as Node) &&
        datasetInputRef.current &&
        !datasetInputRef.current.contains(event.target as Node)
      ) {
        setIsDatasetDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const {
    data: policyData,
    isLoading,
    error,
  } = useGetTeamPolicyApiV1TeamsTeamIdPolicyGet(teamId);

  const updatePolicyMutation = useUpdateTeamPolicyApiV1TeamsTeamIdPolicyPut({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
        });
        toast.success("Policy updated successfully");
      },
      onError: (error: Error) => {
        toast.error(
          `Failed to update policy: ${error.message || "Unknown error"}`,
        );
      },
    },
  });

  const createOverrideMutation =
    useCreatePolicyOverrideApiV1TeamsTeamIdPolicyOverridesPost({
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
          });
          toast.success("Override created successfully");
          setShowOverrideDialog(false);
          setNewOverride({
            datasourceId: dataSources?.[0]?.id || "",
            datasetId: "",
            defaultAction: "",
            autoInvestigateMinSeverity: "",
            reviewRequiredMaxSeverity: "",
          });
          setDatasetSearchTerm("");
          setIsDatasetDropdownOpen(false);
        },
        onError: (error: Error) => {
          toast.error(
            `Failed to create override: ${error.message || "Unknown error"}`,
          );
        },
      },
    });

  const deleteOverrideMutation =
    useDeletePolicyOverrideApiV1TeamsTeamIdPolicyOverridesOverrideIdDelete({
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
          });
          toast.success("Override deleted successfully");
        },
        onError: (error: Error) => {
          toast.error(
            `Failed to delete override: ${error.message || "Unknown error"}`,
          );
        },
      },
    });

  const updateQueueLimitsMutation =
    useUpdateQueueLimitsApiV1TeamsTeamIdPolicyQueueLimitsPut({
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
          });
          toast.success("Queue limits updated successfully");
        },
        onError: (error: Error) => {
          toast.error(
            `Failed to update queue limits: ${error.message || "Unknown error"}`,
          );
        },
      },
    });

  const handleUpdatePolicy = (updates: {
    sources?: string[];
    defaultAction?: string;
    autoInvestigateMinSeverity?: string | null;
    reviewRequiredMaxSeverity?: string | null;
  }) => {
    updatePolicyMutation.mutate({
      teamId,
      data: {
        sources: updates.sources,
        default_action: updates.defaultAction,
        auto_investigate_min_severity: updates.autoInvestigateMinSeverity,
        review_required_max_severity: updates.reviewRequiredMaxSeverity,
      },
    });
  };

  const handleCreateOverride = () => {
    if (!newOverride.datasetId.trim()) {
      toast.error("Dataset ID is required");
      return;
    }
    createOverrideMutation.mutate({
      teamId,
      data: {
        dataset_id: newOverride.datasetId.trim(),
        default_action: newOverride.defaultAction || undefined,
        auto_investigate_min_severity:
          newOverride.autoInvestigateMinSeverity || undefined,
        review_required_max_severity:
          newOverride.reviewRequiredMaxSeverity || undefined,
      },
    });
  };

  const handleDeleteOverride = (overrideId: string) => {
    deleteOverrideMutation.mutate({ teamId, overrideId });
  };

  const handleUpdateQueueLimits = (updates: {
    rateLimitPerMinute?: number;
    burstSize?: number;
    maxConcurrent?: number;
    batchSize?: number;
  }) => {
    updateQueueLimitsMutation.mutate({
      teamId,
      data: {
        rate_limit_per_minute: updates.rateLimitPerMinute,
        burst_size: updates.burstSize,
        max_concurrent: updates.maxConcurrent,
        batch_size: updates.batchSize,
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Failed to load policy"
        description="There was an error loading the team policy. Please try again."
      />
    );
  }

  const policy = policyData?.policy;
  const overrides = policyData?.overrides ?? [];
  const queueLimits = policyData?.queue_limits;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            Policy Settings for {teamName}
          </h2>
          <p className="text-sm text-muted-foreground">
            Configure how alerts are handled for this team
          </p>
        </div>
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>

      {/* Default Policy Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Default Policy</CardTitle>
          <CardDescription>
            These settings apply to all alerts unless overridden by
            dataset-specific rules
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Default Action</Label>
              <Select
                value={policy?.default_action || "issue_only"}
                onValueChange={(value) =>
                  handleUpdatePolicy({ defaultAction: value })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {POLICY_ACTIONS.map((action) => (
                    <SelectItem key={action} value={action}>
                      {action === "auto"
                        ? "Auto Investigate"
                        : action === "review"
                          ? "Require Review"
                          : "Issue Only"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Alert Sources</Label>
              <div className="flex flex-wrap gap-2">
                {ALERT_SOURCES.map((source) => {
                  const isSelected = policy?.sources?.includes(source);
                  return (
                    <Badge
                      key={source}
                      variant={isSelected ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => {
                        const currentSources = policy?.sources || [];
                        const newSources = isSelected
                          ? currentSources.filter((s) => s !== source)
                          : [...currentSources, source];
                        handleUpdatePolicy({ sources: newSources });
                      }}
                    >
                      {source}
                    </Badge>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Auto-investigate Min Severity</Label>
              <Select
                value={policy?.auto_investigate_min_severity || "__none__"}
                onValueChange={(value) =>
                  handleUpdatePolicy({
                    autoInvestigateMinSeverity:
                      value === "__none__" ? null : value,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Not set</SelectItem>
                  {SEVERITY_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Review Required Max Severity</Label>
              <Select
                value={policy?.review_required_max_severity || "__none__"}
                onValueChange={(value) =>
                  handleUpdatePolicy({
                    reviewRequiredMaxSeverity:
                      value === "__none__" ? null : value,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Not set</SelectItem>
                  {SEVERITY_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dataset Overrides */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Dataset Overrides</CardTitle>
              <CardDescription>
                Override default policy settings for specific datasets
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowOverrideDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Override
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {overrides.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No dataset overrides configured
            </p>
          ) : (
            <div className="space-y-3">
              {overrides.map((override: TeamPolicyOverrideResponse) => (
                <div
                  key={override.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="space-y-1">
                    <p className="font-medium">
                      {override.dataset_id || `Tag: ${override.tag_id}`}
                    </p>
                    <div className="flex gap-2">
                      {override.default_action && (
                        <Badge variant="secondary">
                          {override.default_action}
                        </Badge>
                      )}
                      {override.auto_investigate_min_severity && (
                        <Badge variant="outline">
                          Auto: {override.auto_investigate_min_severity}+
                        </Badge>
                      )}
                      {override.review_required_max_severity && (
                        <Badge variant="outline">
                          Review: {override.review_required_max_severity}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDeleteOverride(override.id)}
                    disabled={deleteOverrideMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Queue Limits */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Queue & Rate Limits</CardTitle>
          <CardDescription>
            Control investigation throughput and concurrency for this team
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Rate Limit (per minute)</Label>
              <Input
                type="number"
                value={queueLimits?.rate_limit_per_minute ?? 60}
                onChange={(e) =>
                  handleUpdateQueueLimits({
                    rateLimitPerMinute: parseInt(e.target.value) || 60,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Burst Size</Label>
              <Input
                type="number"
                value={queueLimits?.burst_size ?? 10}
                onChange={(e) =>
                  handleUpdateQueueLimits({
                    burstSize: parseInt(e.target.value) || 10,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Max Concurrent</Label>
              <Input
                type="number"
                value={queueLimits?.max_concurrent ?? 5}
                onChange={(e) =>
                  handleUpdateQueueLimits({
                    maxConcurrent: parseInt(e.target.value) || 5,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Batch Size</Label>
              <Input
                type="number"
                value={queueLimits?.batch_size ?? 5}
                onChange={(e) =>
                  handleUpdateQueueLimits({
                    batchSize: parseInt(e.target.value) || 5,
                  })
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Add Override Dialog */}
      <Dialog open={showOverrideDialog} onOpenChange={setShowOverrideDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Dataset Override</DialogTitle>
            <DialogDescription>
              Create a policy override for a specific dataset
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Datasource and Dataset Picker */}
            <div className="space-y-2">
              <Label>Dataset</Label>
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-2">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <select
                    value={newOverride.datasourceId}
                    onChange={(e) => {
                      setNewOverride({
                        ...newOverride,
                        datasourceId: e.target.value,
                        datasetId: "",
                      });
                      setDatasetSearchTerm("");
                    }}
                    disabled={!dataSources || dataSources.length === 0}
                    className="w-32 rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {!dataSources || dataSources.length === 0 ? (
                      <option value="">No sources</option>
                    ) : (
                      dataSources.map((ds) => (
                        <option key={ds.id} value={ds.id}>
                          {ds.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>

                <div className="relative flex-1">
                  <Input
                    ref={datasetInputRef}
                    value={newOverride.datasetId}
                    onChange={(e) => {
                      setNewOverride({
                        ...newOverride,
                        datasetId: e.target.value,
                      });
                      setIsDatasetDropdownOpen(true);
                    }}
                    onFocus={() => setIsDatasetDropdownOpen(true)}
                    disabled={!newOverride.datasourceId}
                    placeholder={
                      newOverride.datasourceId
                        ? "Search for table..."
                        : "Select a data source first"
                    }
                    className="pr-8"
                  />
                  <Search className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />

                  {isDatasetDropdownOpen && newOverride.datasourceId && (
                    <div
                      ref={datasetDropdownRef}
                      className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-border bg-popover shadow-lg"
                    >
                      {isLoadingTables ? (
                        <div className="flex items-center justify-center p-4">
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        </div>
                      ) : tables && tables.length > 0 ? (
                        <div className="py-1">
                          {tables.slice(0, 10).map((table) => (
                            <button
                              key={table.native_path}
                              type="button"
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                              onClick={() => {
                                setNewOverride({
                                  ...newOverride,
                                  datasetId: table.native_path,
                                });
                                setIsDatasetDropdownOpen(false);
                              }}
                            >
                              <TableIcon className="h-4 w-4 text-muted-foreground" />
                              <span className="font-mono">
                                {table.native_path}
                              </span>
                              <span className="ml-auto text-xs text-muted-foreground">
                                {table.columns.length} cols
                              </span>
                            </button>
                          ))}
                          {tables.length > 10 && (
                            <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
                              +{tables.length - 10} more...
                            </div>
                          )}
                        </div>
                      ) : newOverride.datasetId.length >= 2 ? (
                        <div className="p-3 text-sm text-muted-foreground">
                          No tables found
                        </div>
                      ) : (
                        <div className="p-3 text-sm text-muted-foreground">
                          Type at least 2 characters to search...
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Override Action</Label>
              <Select
                value={newOverride.defaultAction || "__none__"}
                onValueChange={(value) =>
                  setNewOverride({
                    ...newOverride,
                    defaultAction: value === "__none__" ? "" : value,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Use default" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Use default</SelectItem>
                  {POLICY_ACTIONS.map((action) => (
                    <SelectItem key={action} value={action}>
                      {action === "auto"
                        ? "Auto Investigate"
                        : action === "review"
                          ? "Require Review"
                          : "Issue Only"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Auto-investigate Min Severity</Label>
                <Select
                  value={newOverride.autoInvestigateMinSeverity || "__none__"}
                  onValueChange={(value) =>
                    setNewOverride({
                      ...newOverride,
                      autoInvestigateMinSeverity:
                        value === "__none__" ? "" : value,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Use default" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Use default</SelectItem>
                    {SEVERITY_LEVELS.map((level) => (
                      <SelectItem key={level} value={level}>
                        {level.charAt(0).toUpperCase() + level.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Review Required Max Severity</Label>
                <Select
                  value={newOverride.reviewRequiredMaxSeverity || "__none__"}
                  onValueChange={(value) =>
                    setNewOverride({
                      ...newOverride,
                      reviewRequiredMaxSeverity:
                        value === "__none__" ? "" : value,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Use default" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Use default</SelectItem>
                    {SEVERITY_LEVELS.map((level) => (
                      <SelectItem key={level} value={level}>
                        {level.charAt(0).toUpperCase() + level.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowOverrideDialog(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateOverride}
              disabled={createOverrideMutation.isPending}
            >
              {createOverrideMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Create Override
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
