"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

export type DatePickerMode = "single" | "range";

export interface DatePickerValue {
  mode: DatePickerMode;
  start: Date | null;
  end: Date | null;
}

interface QuickSelect {
  label: string;
  getValue: () => DatePickerValue;
}

interface DatePickerProps {
  label?: string;
  value: DatePickerValue;
  onChange: (value: DatePickerValue) => void;
  disabled?: boolean;
  className?: string;
  quickSelects?: QuickSelect[];
  placeholder?: string;
  required?: boolean;
  error?: string;
  hint?: string;
}

const DEFAULT_QUICK_SELECTS: QuickSelect[] = [
  {
    label: "Today",
    getValue: () => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return { mode: "single", start: today, end: today };
    },
  },
  {
    label: "Yesterday",
    getValue: () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      yesterday.setHours(0, 0, 0, 0);
      return { mode: "single", start: yesterday, end: yesterday };
    },
  },
  {
    label: "Last 7 Days",
    getValue: () => {
      const end = new Date();
      end.setHours(0, 0, 0, 0);
      const start = new Date();
      start.setDate(start.getDate() - 7);
      start.setHours(0, 0, 0, 0);
      return { mode: "range", start, end };
    },
  },
  {
    label: "Last 30 Days",
    getValue: () => {
      const end = new Date();
      end.setHours(0, 0, 0, 0);
      const start = new Date();
      start.setDate(start.getDate() - 30);
      start.setHours(0, 0, 0, 0);
      return { mode: "range", start, end };
    },
  },
];

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function isSameDay(a: Date | null, b: Date | null): boolean {
  if (!a || !b) return false;
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function isInRange(date: Date, start: Date | null, end: Date | null): boolean {
  if (!start || !end) return false;
  const d = date.getTime();
  return d >= start.getTime() && d <= end.getTime();
}

export function DatePicker({
  label,
  value,
  onChange,
  disabled = false,
  className,
  quickSelects = DEFAULT_QUICK_SELECTS,
  placeholder = "Select date...",
  required = false,
  error,
  hint,
}: DatePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => value.start || new Date());
  const containerRef = useRef<HTMLDivElement>(null);

  // Format date for display
  const formatDate = useCallback((date: Date | null): string => {
    if (!date) return "";
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }, []);

  const displayValue = useCallback((): string => {
    if (!value.start) return placeholder;
    if (value.mode === "single" || !value.end || isSameDay(value.start, value.end)) {
      return formatDate(value.start);
    }
    return `${formatDate(value.start)} → ${formatDate(value.end)}`;
  }, [value, placeholder, formatDate]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Update view month when value changes externally
  useEffect(() => {
    if (value.start) {
      setViewMonth(value.start);
    }
  }, [value.start]);

  // Generate calendar days for the current view month
  const generateCalendarDays = useCallback((): Array<{ date: Date; isCurrentMonth: boolean }> => {
    const year = viewMonth.getFullYear();
    const month = viewMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = firstDay.getDay();

    const days: Array<{ date: Date; isCurrentMonth: boolean }> = [];

    // Previous month padding
    for (let i = startOffset - 1; i >= 0; i--) {
      const date = new Date(year, month, -i);
      date.setHours(0, 0, 0, 0);
      days.push({ date, isCurrentMonth: false });
    }

    // Current month days
    for (let d = 1; d <= lastDay.getDate(); d++) {
      const date = new Date(year, month, d);
      date.setHours(0, 0, 0, 0);
      days.push({ date, isCurrentMonth: true });
    }

    // Next month padding (fill to 42 = 6 weeks)
    const remaining = 42 - days.length;
    for (let i = 1; i <= remaining; i++) {
      const date = new Date(year, month + 1, i);
      date.setHours(0, 0, 0, 0);
      days.push({ date, isCurrentMonth: false });
    }

    return days;
  }, [viewMonth]);

  const handleDayClick = (date: Date) => {
    if (value.mode === "single") {
      onChange({ mode: "single", start: date, end: date });
      setIsOpen(false);
    } else {
      // Range mode
      if (!value.start || (value.start && value.end)) {
        // Start new range
        onChange({ mode: "range", start: date, end: null });
      } else {
        // Complete the range
        const [start, end] =
          date < value.start ? [date, value.start] : [value.start, date];
        onChange({ mode: "range", start, end });
        setIsOpen(false);
      }
    }
  };

  const handleModeChange = (newMode: DatePickerMode) => {
    if (newMode === "single") {
      onChange({ mode: "single", start: value.start, end: value.start });
    } else {
      onChange({ mode: "range", start: value.start, end: null });
    }
  };

  const navigateMonth = (delta: number) => {
    setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  };

  const isSelected = (date: Date): boolean => {
    if (value.mode === "single") {
      return isSameDay(date, value.start);
    }
    return isSameDay(date, value.start) || isSameDay(date, value.end);
  };

  const isRangeMiddle = (date: Date): boolean => {
    if (value.mode !== "range" || !value.start || !value.end) return false;
    return (
      isInRange(date, value.start, value.end) &&
      !isSameDay(date, value.start) &&
      !isSameDay(date, value.end)
    );
  };

  const isToday = (date: Date): boolean => {
    const today = new Date();
    return isSameDay(date, today);
  };

  return (
    <div ref={containerRef} className={clsx("relative", className)}>
      {label && (
        <label className="mb-1.5 block text-sm font-medium text-foreground">
          {label}
          {required && <span className="ml-1 text-destructive">*</span>}
        </label>
      )}

      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={clsx(
          "flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
          "bg-background text-foreground",
          !disabled && "hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/50",
          disabled && "cursor-not-allowed opacity-50",
          error ? "border-destructive" : "border-border"
        )}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
      >
        <Calendar className="h-4 w-4 flex-shrink-0 text-foreground-muted" />
        <span
          className={clsx(
            "flex-1 truncate",
            value.start ? "text-foreground" : "text-foreground-muted"
          )}
        >
          {displayValue()}
        </span>
      </button>

      {/* Error/Hint Text */}
      {(error || hint) && (
        <p
          className={clsx(
            "mt-1 text-xs",
            error ? "text-destructive" : "text-foreground-muted"
          )}
        >
          {error || hint}
        </p>
      )}

      {/* Dropdown Calendar */}
      {isOpen && (
        <div
          className="absolute z-50 mt-1 w-80 rounded-xl border border-border bg-background p-4 shadow-xl"
          role="dialog"
          aria-label="Date picker"
        >
          {/* Mode Toggle */}
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => handleModeChange("single")}
              className={clsx(
                "flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                value.mode === "single"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background-subtle text-foreground-muted hover:bg-background-elevated"
              )}
            >
              Single Date
            </button>
            <button
              type="button"
              onClick={() => handleModeChange("range")}
              className={clsx(
                "flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                value.mode === "range"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background-subtle text-foreground-muted hover:bg-background-elevated"
              )}
            >
              Date Range
            </button>
          </div>

          {/* Quick Selects */}
          <div className="mb-3 flex flex-wrap gap-1.5">
            {quickSelects.map((qs) => (
              <button
                key={qs.label}
                type="button"
                onClick={() => {
                  const newValue = qs.getValue();
                  onChange(newValue);
                  setIsOpen(false);
                }}
                className="rounded-md bg-background-subtle px-2 py-1 text-xs font-medium text-foreground-muted transition-colors hover:bg-background-elevated hover:text-foreground"
              >
                {qs.label}
              </button>
            ))}
          </div>

          {/* Month Navigation */}
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigateMonth(-1)}
              className="rounded p-1 transition-colors hover:bg-background-subtle"
              aria-label="Previous month"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-medium">
              {viewMonth.toLocaleDateString("en-US", {
                month: "long",
                year: "numeric",
              })}
            </span>
            <button
              type="button"
              onClick={() => navigateMonth(1)}
              className="rounded p-1 transition-colors hover:bg-background-subtle"
              aria-label="Next month"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-0.5 text-center text-xs">
            {/* Weekday Headers */}
            {WEEKDAYS.map((day) => (
              <div
                key={day}
                className="py-1 font-medium text-foreground-muted"
              >
                {day}
              </div>
            ))}

            {/* Day Cells */}
            {generateCalendarDays().map(({ date, isCurrentMonth }, i) => {
              const selected = isSelected(date);
              const rangeMiddle = isRangeMiddle(date);
              const today = isToday(date);

              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleDayClick(date)}
                  className={clsx(
                    "relative rounded-md py-1.5 text-sm transition-colors",
                    // Base states
                    !isCurrentMonth && "text-foreground-muted/40",
                    isCurrentMonth && !selected && !rangeMiddle && "hover:bg-background-subtle",
                    // Selected state
                    selected && "bg-primary text-primary-foreground",
                    // Range middle state
                    rangeMiddle && "bg-primary/20 text-foreground",
                    // Today indicator (ring)
                    today && !selected && "ring-1 ring-primary/50"
                  )}
                  aria-selected={selected}
                  aria-current={today ? "date" : undefined}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>

          {/* Range Selection Hint */}
          {value.mode === "range" && value.start && !value.end && (
            <p className="mt-2 text-center text-xs text-foreground-muted">
              Select end date to complete range
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Helper to convert DatePickerValue to API format
export function datePickerValueToAPI(
  value: DatePickerValue
): { mode: "single" | "range"; start: string; end: string } | null {
  if (!value.start) return null;

  const formatToISO = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  return {
    mode: value.mode,
    start: formatToISO(value.start),
    end: formatToISO(value.end || value.start),
  };
}

// Helper to create empty/default value
export function createEmptyDatePickerValue(): DatePickerValue {
  return { mode: "single", start: null, end: null };
}
