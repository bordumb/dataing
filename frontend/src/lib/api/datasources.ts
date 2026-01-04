import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'

export interface DataSource {
  id: string
  name: string
  type: string
  status: 'connected' | 'disconnected' | 'error'
  created_at: string
  last_synced_at: string | null
  connection_config?: Record<string, unknown>
}

export interface CreateDataSourceRequest {
  name: string
  type: string
  connection_config: {
    host?: string
    port?: number
    database?: string
    username?: string
    password?: string
  }
}

export interface TestConnectionRequest {
  type: string
  connection_config: {
    host?: string
    port?: number
    database?: string
    username?: string
    password?: string
  }
}

const DATASOURCES_KEY = 'datasources'

interface DataSourceListResponse {
  data_sources: DataSource[]
  total: number
}

export function useDataSources() {
  return useQuery({
    queryKey: [DATASOURCES_KEY],
    queryFn: async () => {
      try {
        const response = await customInstance<DataSourceListResponse>({
          url: '/datasources',
          method: 'GET',
        })
        return response.data_sources
      } catch (error) {
        console.error('Failed to fetch datasources:', error)
        throw error
      }
    },
    retry: 1,
    staleTime: 30000,
  })
}

export function useDataSource(id: string) {
  return useQuery({
    queryKey: [DATASOURCES_KEY, id],
    queryFn: () =>
      customInstance<DataSource>({
        url: `/datasources/${id}`,
        method: 'GET',
      }),
    enabled: !!id,
  })
}

export function useCreateDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CreateDataSourceRequest) =>
      customInstance<DataSource>({
        url: '/datasources',
        method: 'POST',
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [DATASOURCES_KEY] })
    },
  })
}

export function useDeleteDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/datasources/${id}`,
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [DATASOURCES_KEY] })
    },
  })
}

export async function createDataSource(data: CreateDataSourceRequest): Promise<DataSource> {
  return customInstance<DataSource>({
    url: '/datasources',
    method: 'POST',
    data,
  })
}

export async function testDataSourceConnection(data: TestConnectionRequest): Promise<{ success: boolean }> {
  try {
    return await customInstance<{ success: boolean }>({
      url: '/datasources/test',
      method: 'POST',
      data,
    })
  } catch {
    throw new Error('Connection test failed')
  }
}

// Schema types
export interface SchemaColumn {
  name: string
  data_type: string
  native_type: string
  nullable: boolean
  is_primary_key: boolean
  description?: string
}

export interface SchemaTable {
  name: string
  table_type: string
  native_type: string
  native_path: string
  columns: SchemaColumn[]
  row_count?: number
}

export interface SchemaSchema {
  name: string
  tables: SchemaTable[]
}

export interface SchemaCatalog {
  name: string
  schemas: SchemaSchema[]
}

export interface SchemaResponse {
  source_id: string
  source_type: string
  source_category: string
  fetched_at: string
  catalogs: SchemaCatalog[]
}

export interface LineageResponse {
  target: string
  upstream: string[]
  downstream: string[]
}

export function useDataSourceSchema(datasourceId: string | null) {
  return useQuery({
    queryKey: ['datasource-schema', datasourceId],
    queryFn: async () => {
      if (!datasourceId) return null
      return customInstance<SchemaResponse>({
        url: `/datasources/${datasourceId}/schema`,
        method: 'GET',
      })
    },
    enabled: !!datasourceId,
  })
}

export function useTableSearch(datasourceId: string | null, searchTerm: string) {
  return useQuery({
    queryKey: ['table-search', datasourceId, searchTerm],
    queryFn: async () => {
      if (!datasourceId) return []
      const schema = await customInstance<SchemaResponse>({
        url: `/datasources/${datasourceId}/schema`,
        method: 'GET',
        params: searchTerm ? { table_pattern: `%${searchTerm}%` } : undefined,
      })
      // Flatten tables from nested structure
      const tables: SchemaTable[] = []
      for (const catalog of schema.catalogs) {
        for (const schemaObj of catalog.schemas) {
          tables.push(...schemaObj.tables)
        }
      }
      // Filter by search term if provided
      if (searchTerm) {
        const term = searchTerm.toLowerCase()
        return tables.filter(t =>
          t.name.toLowerCase().includes(term) ||
          t.native_path.toLowerCase().includes(term)
        )
      }
      return tables
    },
    enabled: !!datasourceId,
    staleTime: 30000, // Cache for 30 seconds
  })
}

export function useSourceTypes() {
  return useQuery({
    queryKey: ['source-types'],
    queryFn: async () => {
      try {
        const response = await customInstance<{ types: SourceTypeInfo[] }>({
          url: '/datasources/types',
          method: 'GET',
        })
        return response.types
      } catch {
        // Fallback source types
        return [
          { type: 'postgresql', display_name: 'PostgreSQL', category: 'database', icon: '🐘' },
          { type: 'mysql', display_name: 'MySQL', category: 'database', icon: '🐬' },
          { type: 'trino', display_name: 'Trino', category: 'database', icon: '⚡' },
          { type: 'snowflake', display_name: 'Snowflake', category: 'database', icon: '❄️' },
          { type: 'bigquery', display_name: 'BigQuery', category: 'database', icon: '📊' },
          { type: 'redshift', display_name: 'Redshift', category: 'database', icon: '🔴' },
          { type: 'duckdb', display_name: 'DuckDB', category: 'database', icon: '🦆' },
          { type: 'mongodb', display_name: 'MongoDB', category: 'database', icon: '🍃' },
          { type: 's3', display_name: 'Amazon S3', category: 'filesystem', icon: '📦' },
        ] as SourceTypeInfo[]
      }
    },
  })
}

export interface SourceTypeInfo {
  type: string
  display_name: string
  category: string
  icon: string
  description?: string
}
