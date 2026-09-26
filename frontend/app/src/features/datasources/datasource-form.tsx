import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { DynamicForm, useDynamicForm } from "@/components/forms";
import {
  createDataSource,
  testDataSourceConnection,
  useSourceTypes,
} from "@/lib/api/datasources";
import { queryKeys } from "@/lib/api/query-keys";

interface DataSourceFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function RequiredMark() {
  return (
    <span aria-hidden="true" className="text-destructive ml-1">
      *
    </span>
  );
}

export function DataSourceForm({ open, onOpenChange }: DataSourceFormProps) {
  const queryClient = useQueryClient();
  const sourceTypes = useSourceTypes();
  const form = useDynamicForm();

  const [name, setName] = React.useState("");
  const [nameError, setNameError] = React.useState<string>();
  const [selectedType, setSelectedType] = React.useState("");

  const chooseType = (type: string) => {
    setSelectedType(type);
    form.reset(sourceTypes.data?.find((t) => t.type === type)?.config_schema);
  };

  const createMutation = useMutation({
    mutationFn: createDataSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.datasources.all });
      onOpenChange(false);
      toast.success("Data source created successfully");
      setName("");
      setSelectedType("");
      form.reset();
    },
    onError: (error) => {
      toast.error(`Failed to create: ${error.message}`);
    },
  });

  const testMutation = useMutation({
    mutationFn: testDataSourceConnection,
    onSuccess: (result) => {
      if (result.success) {
        toast.success("Connection successful!");
      } else {
        toast.error(`Connection failed: ${result.message}`);
      }
    },
    onError: (error) => {
      toast.error(`Connection failed: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const configValid = form.validate();
    const missingName = name.trim() === "";
    setNameError(missingName ? "Name is required" : undefined);
    if (!configValid || missingName) {
      toast.error("Please fix the highlighted fields");
      return;
    }

    createMutation.mutate({
      name: name.trim(),
      type: selectedType,
      config: form.config(),
    });
  };

  const handleTest = () => {
    if (!form.validate()) {
      toast.error("Please fix the highlighted fields");
      return;
    }

    testMutation.mutate({
      type: selectedType,
      config: form.config(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Data Source</DialogTitle>
          <DialogDescription>
            Connect a new data warehouse to investigate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="datasource-name">
                Name
                <RequiredMark />
              </Label>
              <Input
                id="datasource-name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setNameError(undefined);
                }}
                placeholder="Production Warehouse"
                required
                aria-invalid={nameError !== undefined}
              />
              {nameError && (
                <p className="text-sm text-destructive">{nameError}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="datasource-type">
                Type
                <RequiredMark />
              </Label>
              <Select
                value={selectedType}
                onValueChange={chooseType}
                disabled={!sourceTypes.data}
              >
                <SelectTrigger id="datasource-type">
                  <SelectValue
                    placeholder={
                      sourceTypes.isPending ? "Loading types..." : "Select type"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {sourceTypes.data?.map((type) => (
                    <SelectItem key={type.type} value={type.type}>
                      {type.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {sourceTypes.isLoadingError && (
                <p className="text-sm text-destructive">
                  Couldn&apos;t load data source types:{" "}
                  {sourceTypes.error.message}{" "}
                  <button
                    type="button"
                    onClick={() => sourceTypes.refetch()}
                    className="underline underline-offset-4"
                  >
                    Retry
                  </button>
                </p>
              )}
            </div>

            <DynamicForm form={form} />
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={!form.schema || testMutation.isPending}
            >
              {testMutation.isPending ? "Testing..." : "Test Connection"}
            </Button>
            <Button
              type="submit"
              disabled={!form.schema || createMutation.isPending}
            >
              {createMutation.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
