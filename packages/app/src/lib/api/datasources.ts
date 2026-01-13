import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listDatasourcesApiV1DatasourcesGet,
  getDatasourceApiV1DatasourcesDatasourceIdGet,
  createDatasourceApiV1DatasourcesPost,
  deleteDatasourceApiV1DatasourcesDatasourceIdDelete,
  testConnectionApiV1DatasourcesTestPost,
  getDatasourceSchemaApiV1DatasourcesDatasourceIdSchemaGet,
  listSourceTypesApiV1DatasourcesTypesGet,
} from './generated/datasources/datasources'
import type {
  DataSourceResponse,
  CreateDataSourceRequest,
  TestConnectionRequest,
  TestConnectionResponse,
} from './model'
import { queryKeys } from './query-keys'

// Re-export types
export type { DataSourceResponse, CreateDataSourceRequest, TestConnectionRequest }
export type DataSource = DataSourceResponse

// For backwards compatibility with existing code
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

export function useDataSources() {
  return useQuery({
    queryKey: queryKeys.datasources.all,
    queryFn: async () => {
      try {
        const response = await listDatasourcesApiV1DatasourcesGet()
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
    queryKey: queryKeys.datasources.detail(id),
    queryFn: () => getDatasourceApiV1DatasourcesDatasourceIdGet(id),
    enabled: !!id,
  })
}

export function useCreateDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CreateDataSourceRequest) =>
      createDatasourceApiV1DatasourcesPost(data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.datasources.all,
      })
    },
  })
}

export function useDeleteDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      deleteDatasourceApiV1DatasourcesDatasourceIdDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.datasources.all,
      })
    },
  })
}

export async function createDataSource(
  data: CreateDataSourceRequest
): Promise<DataSourceResponse> {
  return createDatasourceApiV1DatasourcesPost(data)
}

export async function testDataSourceConnection(
  data: TestConnectionRequest
): Promise<TestConnectionResponse> {
  try {
    return await testConnectionApiV1DatasourcesTestPost(data)
  } catch {
    throw new Error('Connection test failed')
  }
}

export function useDataSourceSchema(datasourceId: string | null) {
  return useQuery({
    queryKey: datasourceId ? queryKeys.datasources.schema(datasourceId) : ['disabled'],
    queryFn: async () => {
      if (!datasourceId) return null
      return getDatasourceSchemaApiV1DatasourcesDatasourceIdSchemaGet(
        datasourceId
      )
    },
    enabled: !!datasourceId,
  })
}

export function useTableSearch(datasourceId: string | null, searchTerm: string) {
  return useQuery({
    queryKey: datasourceId
      ? queryKeys.datasources.schema(datasourceId, { search: searchTerm })
      : ['disabled'],
    queryFn: async () => {
      if (!datasourceId) return []
      const schema = await getDatasourceSchemaApiV1DatasourcesDatasourceIdSchemaGet(
        datasourceId,
        searchTerm ? { table_pattern: `%${searchTerm}%` } : undefined
      )
      // Flatten tables from nested structure
      const tables: SchemaTable[] = []
      const catalogs = schema.catalogs as unknown as SchemaCatalog[]
      for (const catalog of catalogs) {
        for (const schemaObj of catalog.schemas) {
          tables.push(...schemaObj.tables)
        }
      }
      // Filter by search term if provided
      if (searchTerm) {
        const term = searchTerm.toLowerCase()
        return tables.filter(
          (t) =>
            t.name.toLowerCase().includes(term) ||
            t.native_path.toLowerCase().includes(term)
        )
      }
      return tables
    },
    enabled: !!datasourceId,
    staleTime: 30000,
  })
}

export interface SourceTypeInfo {
  type: string
  display_name: string
  category: string
  icon: string
  description?: string
  config_schema?: Record<string, unknown>
}

export function useSourceTypes() {
  return useQuery({
    queryKey: queryKeys.datasources.types,
    queryFn: async () => {
      try {
        const response = await listSourceTypesApiV1DatasourcesTypesGet()
        return response.types as SourceTypeInfo[]
      } catch {
        // Fallback source types
        return [
          { type: 'postgresql', display_name: 'PostgreSQL', category: 'database', icon: '' },
          { type: 'mysql', display_name: 'MySQL', category: 'database', icon: '' },
          { type: 'trino', display_name: 'Trino', category: 'database', icon: '' },
          { type: 'snowflake', display_name: 'Snowflake', category: 'database', icon: '' },
          { type: 'bigquery', display_name: 'BigQuery', category: 'database', icon: '' },
          { type: 'redshift', display_name: 'Redshift', category: 'database', icon: '' },
          { type: 'duckdb', display_name: 'DuckDB', category: 'database', icon: '' },
          { type: 'mongodb', display_name: 'MongoDB', category: 'database', icon: '' },
          { type: 's3', display_name: 'Amazon S3', category: 'filesystem', icon: '' },
        ] as SourceTypeInfo[]
      }
    },
  })
}
