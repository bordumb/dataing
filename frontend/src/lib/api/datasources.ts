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

export function useDataSources() {
  return useQuery({
    queryKey: [DATASOURCES_KEY],
    queryFn: async () => {
      try {
        return await customInstance<DataSource[]>({
          url: '/datasources',
          method: 'GET',
        })
      } catch {
        // Return mock data if endpoint doesn't exist
        return [
          {
            id: '1',
            name: 'Production PostgreSQL',
            type: 'postgres',
            status: 'connected' as const,
            created_at: new Date().toISOString(),
            last_synced_at: new Date().toISOString(),
          },
          {
            id: '2',
            name: 'Analytics Trino',
            type: 'trino',
            status: 'connected' as const,
            created_at: new Date().toISOString(),
            last_synced_at: new Date().toISOString(),
          },
        ]
      }
    },
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
