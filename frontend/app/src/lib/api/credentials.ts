/**
 * A person's own login for a datasource (spec 0001 D3). The issue agent's
 * queries run with it, so the database enforces that person's permissions.
 * The API never returns the password.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteCredentialsApiV1DatasourcesDatasourceIdCredentialsDelete,
  getCredentialsStatusApiV1DatasourcesDatasourceIdCredentialsGet,
  saveCredentialsApiV1DatasourcesDatasourceIdCredentialsPost,
  testCredentialsApiV1DatasourcesDatasourceIdCredentialsTestPost,
} from "./generated/credentials/credentials";
import type { SaveCredentialsRequest } from "./model";
import { queryKeys } from "./query-keys";

export type { SaveCredentialsRequest };

/** Whether the signed-in person has saved a login for the datasource. */
export function useCredentialsStatus(datasourceId: string) {
  return useQuery({
    queryKey: queryKeys.credentials.status(datasourceId),
    queryFn: () =>
      getCredentialsStatusApiV1DatasourcesDatasourceIdCredentialsGet(
        datasourceId,
      ),
    enabled: !!datasourceId,
  });
}

/**
 * Connect with a login first and save it only if the database accepts it, so a
 * typo fails here instead of in the middle of a conversation with the agent.
 */
export function useSaveCredentials(datasourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (login: SaveCredentialsRequest) => {
      const test =
        await testCredentialsApiV1DatasourcesDatasourceIdCredentialsTestPost(
          datasourceId,
          login,
        );
      if (!test.success) {
        throw new Error(
          `Couldn't connect with this login: ${test.error || "the database refused it."}`,
        );
      }
      return saveCredentialsApiV1DatasourcesDatasourceIdCredentialsPost(
        datasourceId,
        login,
      );
    },
    onSuccess: (status) => {
      queryClient.setQueryData(
        queryKeys.credentials.status(datasourceId),
        status,
      );
    },
  });
}

export function useDeleteCredentials(datasourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      deleteCredentialsApiV1DatasourcesDatasourceIdCredentialsDelete(
        datasourceId,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.credentials.status(datasourceId),
      }),
  });
}
