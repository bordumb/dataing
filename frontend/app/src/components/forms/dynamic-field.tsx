import type { ReactElement } from "react";

import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ConfigField } from "@/lib/api/model";

/** Form-state value of a field: "" when empty, a number for integers. */
export type FieldValue = string | number | boolean;

interface DynamicFieldProps {
  field: ConfigField;
  value: FieldValue;
  onChange: (name: string, value: FieldValue) => void;
  error?: string;
}

interface ControlProps {
  id: string;
  field: ConfigField;
  value: FieldValue;
  invalid: boolean;
  onChange: (value: FieldValue) => void;
}

// Every ConfigField type needs a case: a type added to the backend's
// ConfigField literal fails typecheck here once the client is regenerated.
function FieldControl({
  id,
  field,
  value,
  invalid,
  onChange,
}: ControlProps): ReactElement {
  const placeholder = field.placeholder ?? undefined;

  switch (field.type) {
    case "string":
    case "secret":
      return (
        <Input
          id={id}
          type={field.type === "secret" ? "password" : "text"}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={field.required}
          aria-invalid={invalid}
        />
      );

    case "integer":
      return (
        <Input
          id={id}
          type="number"
          step={1}
          min={field.min_value ?? undefined}
          max={field.max_value ?? undefined}
          value={value === "" ? "" : Number(value)}
          onChange={(e) =>
            onChange(e.target.value === "" ? "" : Number(e.target.value))
          }
          placeholder={placeholder}
          required={field.required}
          aria-invalid={invalid}
        />
      );

    case "boolean":
      return (
        <Checkbox
          id={id}
          checked={value === true}
          onCheckedChange={(checked) => onChange(checked === true)}
          aria-invalid={invalid}
        />
      );

    case "enum":
      return (
        <Select value={String(value)} onValueChange={onChange}>
          <SelectTrigger id={id} aria-invalid={invalid}>
            <SelectValue placeholder={placeholder ?? "Select..."} />
          </SelectTrigger>
          <SelectContent>
            {field.options?.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );

    case "json":
      return (
        <Textarea
          id={id}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={field.required}
          aria-invalid={invalid}
          rows={4}
          className="font-mono text-xs"
        />
      );

    case "file":
      // The file's text travels in the JSON config.
      return (
        <Input
          id={id}
          type="file"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            onChange(file ? await file.text() : "");
          }}
          required={field.required}
          aria-invalid={invalid}
        />
      );
  }
}

export function DynamicField({
  field,
  value,
  onChange,
  error,
}: DynamicFieldProps) {
  const id = `config-${field.name}`;
  const control = (
    <FieldControl
      id={id}
      field={field}
      value={value}
      invalid={error !== undefined}
      onChange={(next) => onChange(field.name, next)}
    />
  );

  return (
    <div className="space-y-2">
      {field.type === "boolean" ? (
        <div className="flex items-center gap-2">
          {control}
          <Label htmlFor={id} className="font-normal">
            {field.label}
          </Label>
        </div>
      ) : (
        <>
          <Label htmlFor={id}>
            {field.label}
            {field.required && (
              <span aria-hidden="true" className="text-destructive ml-1">
                *
              </span>
            )}
          </Label>
          {control}
        </>
      )}
      {(field.description || field.help_url) && (
        <p className="text-sm text-muted-foreground">
          {field.description}
          {field.help_url && (
            <>
              {field.description && " "}
              <a
                href={field.help_url}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-4"
              >
                Docs
              </a>
            </>
          )}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
