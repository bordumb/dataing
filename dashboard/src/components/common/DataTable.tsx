"use client";

import { useMemo, useState } from "react";
import { FilterBar, FilterOption } from "@/components/common/FilterBar";
import { Pagination } from "@/components/common/Pagination";
import { SearchInput } from "@/components/common/SearchInput";

interface Column<T> {
  key: string;
  label: string;
  render?: (item: T) => React.ReactNode;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  searchKeys?: (keyof T)[];
  filterOptions?: FilterOption[];
  pageSize?: number;
}

export function DataTable<T extends Record<string, any>>({
  data,
  columns,
  searchKeys = [],
  filterOptions = [],
  pageSize = 8,
}: DataTableProps<T>) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Record<string, string>>({});

  const filtered = useMemo(() => {
    let result = [...data];
    if (query && searchKeys.length > 0) {
      const needle = query.toLowerCase();
      result = result.filter((item) =>
        searchKeys.some((key) => String(item[key] ?? "").toLowerCase().includes(needle)),
      );
    }
    if (filterOptions.length > 0) {
      result = result.filter((item) =>
        filterOptions.every((filter) => {
          const value = filters[filter.key];
          if (!value) return true;
          return String(item[filter.key] ?? "") === value;
        }),
      );
    }
    return result;
  }, [data, query, searchKeys, filterOptions, filters]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full max-w-sm">
          <SearchInput value={query} onChange={setQuery} placeholder="Search" />
        </div>
        {filterOptions.length > 0 && (
          <FilterBar
            filters={filterOptions}
            onChange={(key, value) => {
              setFilters((prev) => ({ ...prev, [key]: value }));
              setPage(1);
            }}
          />
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-background-elevated/80">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-background-elevated/60 text-xs uppercase tracking-widest text-foreground-muted">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-4 py-3">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((item, index) => (
              <tr key={index} className="border-b border-border last:border-0">
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3">
                    {column.render ? column.render(item) : String(item[column.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
}
