import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listDatasourceDatasetsApiV1DatasourcesDatasourceIdDatasetsGet,
  syncDatasourceSchemaApiV1DatasourcesDatasourceIdSyncPost,
} from './generated/datasources/datasources'
import {
  getDatasetApiV1DatasetsDatasetIdGet,
  getDatasetInvestigationsApiV1DatasetsDatasetIdInvestigationsGet,
} from './generated/datasets/datasets'
import type {
  DatasetSummary,
  DatasetDetailResponse,
  DatasourceDatasetsResponse,
  DatasetInvestigationsResponse,
  InvestigationSummary,
  SyncResponse,
} from './model'
import { queryKeys } from './query-keys'

// Re-export types for convenience
export type { DatasetSummary, DatasetDetailResponse, InvestigationSummary, SyncResponse }
export type Dataset = DatasetSummary
export type DatasetDetail = DatasetDetailResponse
export type DatasetListResponse = DatasourceDatasetsResponse

/**
 * Hook to fetch datasets for a datasource.
 */
export function useDatasets(datasourceId: string | null) {
  return useQuery({
    queryKey: datasourceId ? queryKeys.datasets.all(datasourceId) : ['disabled'],
    queryFn: async (): Promise<DatasourceDatasetsResponse> => {
      if (!datasourceId) throw new Error('No datasource ID')
      return listDatasourceDatasetsApiV1DatasourcesDatasourceIdDatasetsGet(datasourceId)
    },
    enabled: !!datasourceId,
  })
}

/**
 * Hook to fetch a single dataset with column details.
 */
export function useDataset(datasetId: string | null) {
  return useQuery({
    queryKey: datasetId ? queryKeys.datasets.detail(datasetId) : ['disabled'],
    queryFn: async (): Promise<DatasetDetailResponse> => {
      if (!datasetId) throw new Error('No dataset ID')
      return getDatasetApiV1DatasetsDatasetIdGet(datasetId)
    },
    enabled: !!datasetId,
  })
}

/**
 * Hook to fetch investigations for a dataset.
 */
export function useDatasetInvestigations(datasetId: string | null) {
  return useQuery({
    queryKey: datasetId ? queryKeys.datasets.investigations(datasetId) : ['disabled'],
    queryFn: async (): Promise<DatasetInvestigationsResponse> => {
      if (!datasetId) throw new Error('No dataset ID')
      return getDatasetInvestigationsApiV1DatasetsDatasetIdInvestigationsGet(datasetId)
    },
    enabled: !!datasetId,
  })
}

/**
 * Hook to sync a datasource's schema and update datasets.
 */
export function useSyncDatasource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (datasourceId: string): Promise<SyncResponse> => {
      return syncDatasourceSchemaApiV1DatasourcesDatasourceIdSyncPost(datasourceId)
    },
    onSuccess: (_, datasourceId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.datasets.all(datasourceId),
      })
    },
  })
}
