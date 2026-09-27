import { useCallback, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import type { ConfigField, ConfigSchema, FieldGroup } from "@/lib/api/model";
import { cn } from "@/lib/utils";
import { DynamicField, type FieldValue } from "./dynamic-field";

type FormValues = Record<string, FieldValue>;
type FormErrors = Record<string, string>;

function initialValue(field: ConfigField): FieldValue {
  const value = field.default_value;
  switch (field.type) {
    case "boolean":
      return value === true;
    case "integer":
      return typeof value === "number" ? value : "";
    case "json":
      return value == null ? "" : JSON.stringify(value, null, 2);
    default:
      return value == null ? "" : String(value);
  }
}

function initialValues(schema: ConfigSchema): FormValues {
  return Object.fromEntries(
    schema.fields.map((field) => [field.name, initialValue(field)]),
  );
}

function isShown(field: ConfigField, values: FormValues): boolean {
  if (!field.show_if) return true;
  return values[String(field.show_if.field)] === field.show_if.value;
}

function fieldError(field: ConfigField, value: FieldValue): string | undefined {
  if (value === "") {
    return field.required ? `${field.label} is required` : undefined;
  }
  switch (field.type) {
    case "integer":
      if (typeof value !== "number" || !Number.isInteger(value)) {
        return `${field.label} must be a whole number`;
      }
      if (field.min_value != null && value < field.min_value) {
        return `${field.label} must be at least ${field.min_value}`;
      }
      if (field.max_value != null && value > field.max_value) {
        return `${field.label} must be at most ${field.max_value}`;
      }
      return undefined;
    case "json":
      try {
        JSON.parse(String(value));
        return undefined;
      } catch {
        return `${field.label} must be valid JSON`;
      }
    default:
      if (field.pattern && !new RegExp(field.pattern).test(String(value))) {
        return `${field.label} format is invalid`;
      }
      return undefined;
  }
}

function validateValues(schema: ConfigSchema, values: FormValues): FormErrors {
  const errors: FormErrors = {};
  for (const field of schema.fields) {
    if (!isShown(field, values)) continue;
    const error = fieldError(field, values[field.name]);
    if (error) errors[field.name] = error;
  }
  return errors;
}

// Hidden and empty fields are left out so the adapter applies its own defaults.
function toConfig(
  schema: ConfigSchema,
  values: FormValues,
): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  for (const field of schema.fields) {
    const value = values[field.name];
    if (!isShown(field, values) || value === "") continue;
    config[field.name] =
      field.type === "json" ? JSON.parse(String(value)) : value;
  }
  return config;
}

interface FormState {
  schema?: ConfigSchema;
  values: FormValues;
  errors: FormErrors;
  openGroups: Record<string, boolean>;
}

function initialState(schema?: ConfigSchema): FormState {
  if (!schema) return { values: {}, errors: {}, openGroups: {} };
  return {
    schema,
    values: initialValues(schema),
    errors: {},
    openGroups: Object.fromEntries(
      schema.field_groups.map((group) => [
        group.id,
        !group.collapsed_by_default,
      ]),
    ),
  };
}

/** State for a form rendered from an adapter's backend config schema. */
export function useDynamicForm() {
  const [state, setState] = useState<FormState>(initialState);

  /** Swap in a schema (or none), starting from its default values. */
  const reset = useCallback((schema?: ConfigSchema) => {
    setState(initialState(schema));
  }, []);

  const setValue = useCallback((name: string, value: FieldValue) => {
    setState((prev) => {
      const errors = { ...prev.errors };
      delete errors[name];
      return { ...prev, values: { ...prev.values, [name]: value }, errors };
    });
  }, []);

  const toggleGroup = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      openGroups: { ...prev.openGroups, [id]: !prev.openGroups[id] },
    }));
  }, []);

  /**
   * Check the visible fields and record their errors, opening every group
   * that holds one. Reports whether the form is valid.
   */
  const validate = (): boolean => {
    const fields = state.schema?.fields ?? [];
    const errors = state.schema
      ? validateValues(state.schema, state.values)
      : {};
    const withErrors = fields
      .filter((field) => errors[field.name])
      .map((field) => [field.group, true]);
    setState((prev) => ({
      ...prev,
      errors,
      openGroups: { ...prev.openGroups, ...Object.fromEntries(withErrors) },
    }));
    return Object.keys(errors).length === 0;
  };

  /** The adapter config the current values describe. */
  const config = (): Record<string, unknown> =>
    state.schema ? toConfig(state.schema, state.values) : {};

  return { ...state, reset, setValue, toggleGroup, validate, config };
}

export type DynamicFormState = ReturnType<typeof useDynamicForm>;

interface FieldGroupSectionProps {
  group: FieldGroup;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}

function FieldGroupSection({
  group,
  open,
  onToggle,
  children,
}: FieldGroupSectionProps) {
  return (
    <section className="rounded-md border">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn("h-4 w-4 transition-transform", open && "rotate-90")}
        />
        {group.label}
      </button>
      {open && (
        <div className="space-y-4 px-3 pb-3">
          {group.description && (
            <p className="text-sm text-muted-foreground">{group.description}</p>
          )}
          {children}
        </div>
      )}
    </section>
  );
}

/** Renders a schema's fields in its field groups, collapsing as it asks. */
export function DynamicForm({ form }: { form: DynamicFormState }) {
  const { schema, values, errors, openGroups, setValue, toggleGroup } = form;

  if (!schema) return null;

  return (
    <div className="space-y-3">
      {schema.field_groups.map((group) => {
        const fields = schema.fields.filter(
          (field) => field.group === group.id && isShown(field, values),
        );
        if (fields.length === 0) return null;

        return (
          <FieldGroupSection
            key={group.id}
            group={group}
            open={openGroups[group.id]}
            onToggle={() => toggleGroup(group.id)}
          >
            {fields.map((field) => (
              <DynamicField
                key={field.name}
                field={field}
                value={values[field.name]}
                onChange={setValue}
                error={errors[field.name]}
              />
            ))}
          </FieldGroupSection>
        );
      })}
    </div>
  );
}
