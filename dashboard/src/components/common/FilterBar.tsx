"use client";

import { Select } from "@/components/ui/Select";

export interface FilterOption {
  key: string;
  label: string;
  options: string[];
}

export function FilterBar({
  filters,
  onChange,
}: {
  filters: FilterOption[];
  onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3">
      {filters.map((filter) => (
        <Select
          key={filter.key}
          label={filter.label}
          onChange={(event) => onChange(filter.key, event.target.value)}
        >
          <option value="">All</option>
          {filter.options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </Select>
      ))}
    </div>
  );
}
