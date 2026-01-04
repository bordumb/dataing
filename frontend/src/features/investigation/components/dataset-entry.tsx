import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useTableSearch, SchemaTable } from '@/lib/api/datasources'
import {
  Database,
  Server,
  HardDrive,
  Zap,
  Table as TableIcon,
  Search,
  Loader2,
  X,
} from 'lucide-react'

// Source type icons
const SOURCE_ICONS: Record<string, typeof Database> = {
  postgresql: Database,
  postgres: Database,
  mysql: Server,
  trino: Database,
  snowflake: Database,
  bigquery: Database,
  redshift: Database,
  duckdb: Database,
  mongodb: Database,
  dynamodb: Zap,
  cassandra: Database,
  s3: HardDrive,
  gcs: HardDrive,
  hdfs: HardDrive,
  salesforce: Database,
  hubspot: Database,
  stripe: Database,
}

interface DataSourceOption {
  id: string
  name: string
  type: string
}

interface DatasetEntryProps {
  datasourceId: string
  datasourceType: string
  identifier: string
  onDatasourceChange: (id: string) => void
  onIdentifierChange: (value: string) => void
  onRemove: () => void
  canRemove: boolean
  disabled?: boolean
  autoFocus?: boolean
  dataSources: DataSourceOption[]
  onTableSelect: (table: SchemaTable) => void
}

export function DatasetEntry({
  datasourceId,
  datasourceType,
  identifier,
  onDatasourceChange,
  onIdentifierChange,
  onRemove,
  canRemove,
  disabled,
  autoFocus,
  dataSources,
  onTableSelect,
}: DatasetEntryProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const { data: tables, isLoading } = useTableSearch(datasourceId, searchTerm)

  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(identifier), 300)
    return () => clearTimeout(timer)
  }, [identifier])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (table: SchemaTable) => {
    onIdentifierChange(table.native_path)
    onTableSelect(table)
    setIsOpen(false)
  }

  const Icon = SOURCE_ICONS[datasourceType] || Database

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-2">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <select
          value={datasourceId}
          onChange={(e) => onDatasourceChange(e.target.value)}
          disabled={disabled || dataSources.length === 0}
          className="w-32 rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {dataSources.length === 0 ? (
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
          ref={inputRef}
          value={identifier}
          onChange={(e) => {
            onIdentifierChange(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          disabled={disabled || !datasourceId}
          autoFocus={autoFocus}
          placeholder={datasourceId ? 'Search for table...' : 'Select a data source first'}
          className="pr-8"
        />
        <Search className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />

        {isOpen && datasourceId && (
          <div
            ref={dropdownRef}
            className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-popover shadow-lg"
          >
            {isLoading ? (
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
                    onClick={() => handleSelect(table)}
                  >
                    <TableIcon className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono">{table.native_path}</span>
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
            ) : identifier.length >= 2 ? (
              <div className="p-3 text-sm text-muted-foreground">No tables found</div>
            ) : (
              <div className="p-3 text-sm text-muted-foreground">
                Type at least 2 characters to search...
              </div>
            )}
          </div>
        )}
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onRemove}
        disabled={disabled || !canRemove}
        className="h-8 w-8 text-muted-foreground hover:text-destructive"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

// Re-export the SOURCE_ICONS for use in other components if needed
export { SOURCE_ICONS }
