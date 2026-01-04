import { useState, useRef, useEffect, useCallback } from 'react'
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export type DatePickerMode = 'single' | 'range'

export interface DatePickerValue {
  mode: DatePickerMode
  start: Date | null
  end: Date | null
}

interface QuickSelect {
  label: string
  getValue: () => DatePickerValue
}

interface DatePickerProps {
  label?: string
  value: DatePickerValue
  onChange: (value: DatePickerValue) => void
  disabled?: boolean
  className?: string
  quickSelects?: QuickSelect[]
  placeholder?: string
  required?: boolean
  error?: string
  hint?: string
}

const DEFAULT_QUICK_SELECTS: QuickSelect[] = [
  {
    label: 'Today',
    getValue: () => {
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return { mode: 'single', start: today, end: today }
    },
  },
  {
    label: 'Yesterday',
    getValue: () => {
      const yesterday = new Date()
      yesterday.setDate(yesterday.getDate() - 1)
      yesterday.setHours(0, 0, 0, 0)
      return { mode: 'single', start: yesterday, end: yesterday }
    },
  },
  {
    label: 'Last 7 Days',
    getValue: () => {
      const end = new Date()
      end.setHours(0, 0, 0, 0)
      const start = new Date()
      start.setDate(start.getDate() - 7)
      start.setHours(0, 0, 0, 0)
      return { mode: 'range', start, end }
    },
  },
  {
    label: 'Last 30 Days',
    getValue: () => {
      const end = new Date()
      end.setHours(0, 0, 0, 0)
      const start = new Date()
      start.setDate(start.getDate() - 30)
      start.setHours(0, 0, 0, 0)
      return { mode: 'range', start, end }
    },
  },
]

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

function isSameDay(a: Date | null, b: Date | null): boolean {
  if (!a || !b) return false
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function isInRange(date: Date, start: Date | null, end: Date | null): boolean {
  if (!start || !end) return false
  const d = date.getTime()
  return d >= start.getTime() && d <= end.getTime()
}

export function DatePicker({
  label,
  value,
  onChange,
  disabled = false,
  className,
  quickSelects = DEFAULT_QUICK_SELECTS,
  placeholder = 'Select date...',
  required = false,
  error,
  hint,
}: DatePickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => value.start || new Date())
  const containerRef = useRef<HTMLDivElement>(null)

  const formatDate = useCallback((date: Date | null): string => {
    if (!date) return ''
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }, [])

  const displayValue = useCallback((): string => {
    if (!value.start) return placeholder
    if (value.mode === 'single' || !value.end || isSameDay(value.start, value.end)) {
      return formatDate(value.start)
    }
    return `${formatDate(value.start)} - ${formatDate(value.end)}`
  }, [value, placeholder, formatDate])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    if (value.start) {
      setViewMonth(value.start)
    }
  }, [value.start])

  const generateCalendarDays = useCallback((): Array<{ date: Date; isCurrentMonth: boolean }> => {
    const year = viewMonth.getFullYear()
    const month = viewMonth.getMonth()
    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)
    const startOffset = firstDay.getDay()

    const days: Array<{ date: Date; isCurrentMonth: boolean }> = []

    for (let i = startOffset - 1; i >= 0; i--) {
      const date = new Date(year, month, -i)
      date.setHours(0, 0, 0, 0)
      days.push({ date, isCurrentMonth: false })
    }

    for (let d = 1; d <= lastDay.getDate(); d++) {
      const date = new Date(year, month, d)
      date.setHours(0, 0, 0, 0)
      days.push({ date, isCurrentMonth: true })
    }

    const remaining = 42 - days.length
    for (let i = 1; i <= remaining; i++) {
      const date = new Date(year, month + 1, i)
      date.setHours(0, 0, 0, 0)
      days.push({ date, isCurrentMonth: false })
    }

    return days
  }, [viewMonth])

  const handleDayClick = (date: Date) => {
    if (value.mode === 'single') {
      onChange({ mode: 'single', start: date, end: date })
      setIsOpen(false)
    } else {
      if (!value.start || (value.start && value.end)) {
        onChange({ mode: 'range', start: date, end: null })
      } else {
        const [start, end] =
          date < value.start ? [date, value.start] : [value.start, date]
        onChange({ mode: 'range', start, end })
        setIsOpen(false)
      }
    }
  }

  const handleModeChange = (newMode: DatePickerMode) => {
    if (newMode === 'single') {
      onChange({ mode: 'single', start: value.start, end: value.start })
    } else {
      onChange({ mode: 'range', start: value.start, end: null })
    }
  }

  const navigateMonth = (delta: number) => {
    setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1))
  }

  const isSelected = (date: Date): boolean => {
    if (value.mode === 'single') {
      return isSameDay(date, value.start)
    }
    return isSameDay(date, value.start) || isSameDay(date, value.end)
  }

  const isRangeMiddle = (date: Date): boolean => {
    if (value.mode !== 'range' || !value.start || !value.end) return false
    return (
      isInRange(date, value.start, value.end) &&
      !isSameDay(date, value.start) &&
      !isSameDay(date, value.end)
    )
  }

  const isToday = (date: Date): boolean => {
    const today = new Date()
    return isSameDay(date, today)
  }

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      {label && (
        <label className="mb-1.5 block text-sm font-medium">
          {label}
          {required && <span className="ml-1 text-destructive">*</span>}
        </label>
      )}

      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors',
          'bg-background',
          !disabled && 'hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          disabled && 'cursor-not-allowed opacity-50',
          error ? 'border-destructive' : 'border-input'
        )}
      >
        <Calendar className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        <span className={cn('flex-1 truncate', value.start ? '' : 'text-muted-foreground')}>
          {displayValue()}
        </span>
      </button>

      {(error || hint) && (
        <p className={cn('mt-1 text-xs', error ? 'text-destructive' : 'text-muted-foreground')}>
          {error || hint}
        </p>
      )}

      {isOpen && (
        <div className="absolute z-50 mt-1 w-80 rounded-lg border border-border bg-popover p-4 shadow-lg">
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => handleModeChange('single')}
              className={cn(
                'flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                value.mode === 'single'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              )}
            >
              Single Date
            </button>
            <button
              type="button"
              onClick={() => handleModeChange('range')}
              className={cn(
                'flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                value.mode === 'range'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              )}
            >
              Date Range
            </button>
          </div>

          <div className="mb-3 flex flex-wrap gap-1.5">
            {quickSelects.map((qs) => (
              <button
                key={qs.label}
                type="button"
                onClick={() => {
                  const newValue = qs.getValue()
                  onChange(newValue)
                  setIsOpen(false)
                }}
                className="rounded-md bg-muted px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
              >
                {qs.label}
              </button>
            ))}
          </div>

          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigateMonth(-1)}
              className="rounded p-1 transition-colors hover:bg-muted"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-medium">
              {viewMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
            </span>
            <button
              type="button"
              onClick={() => navigateMonth(1)}
              className="rounded p-1 transition-colors hover:bg-muted"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-0.5 text-center text-xs">
            {WEEKDAYS.map((day) => (
              <div key={day} className="py-1 font-medium text-muted-foreground">
                {day}
              </div>
            ))}

            {generateCalendarDays().map(({ date, isCurrentMonth }, i) => {
              const selected = isSelected(date)
              const rangeMiddle = isRangeMiddle(date)
              const today = isToday(date)

              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleDayClick(date)}
                  className={cn(
                    'relative rounded-md py-1.5 text-sm transition-colors',
                    !isCurrentMonth && 'text-muted-foreground/40',
                    isCurrentMonth && !selected && !rangeMiddle && 'hover:bg-muted',
                    selected && 'bg-primary text-primary-foreground',
                    rangeMiddle && 'bg-primary/20',
                    today && !selected && 'ring-1 ring-primary/50'
                  )}
                >
                  {date.getDate()}
                </button>
              )
            })}
          </div>

          {value.mode === 'range' && value.start && !value.end && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Select end date to complete range
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function datePickerValueToString(value: DatePickerValue): string | null {
  if (!value.start) return null
  const year = value.start.getFullYear()
  const month = String(value.start.getMonth() + 1).padStart(2, '0')
  const day = String(value.start.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function stringToDatePickerValue(dateStr: string): DatePickerValue {
  const date = new Date(dateStr + 'T00:00:00')
  return { mode: 'single', start: date, end: date }
}

export function createEmptyDatePickerValue(): DatePickerValue {
  return { mode: 'single', start: null, end: null }
}
