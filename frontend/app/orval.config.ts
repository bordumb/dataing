import { defineConfig } from 'orval';

// Orval 8 settings that keep the client's orval 6 shapes. Leave
// override.query.useQuery/useMutation unset: orval 8 applies them to every
// verb, and a GET with both becomes a mutation. Unset, GETs get query hooks
// and the other verbs get mutation hooks.
export default defineConfig({
  dataing: {
    input: {
      target: '../../python-packages/dataing/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/lib/api/generated',
      schemas: 'src/lib/api/model',
      client: 'react-query',
      // customInstance takes one request config ({ url, method, params, data,
      // signal }), which is what the axios client passes to a mutator. The
      // default fetch client would call it as (url, init). Nothing imports
      // axios: customInstance makes the request.
      httpClient: 'axios',
      mock: false,
      // Orval 6 sorted model properties alphabetically.
      propertySortOrder: 'Alphabetical',
      // Orval picks import extensions from tsconfig.json, where Vite's
      // allowImportingTsExtensions makes it write "../../client.ts". The same
      // module settings without that flag keep imports extensionless.
      tsconfig: {
        compilerOptions: {
          module: 'ESNext',
          moduleResolution: 'bundler',
        },
      },
      override: {
        mutator: {
          path: './src/lib/api/client.ts',
          name: 'customInstance',
        },
        // Orval 6 named nullable property types (FooBar = string | null);
        // orval 8 inlines them unless this is set.
        aliasCombinedTypes: true,
      },
    },
    hooks: {
      afterAllFilesWrite: 'prettier --write',
    },
  },
});
