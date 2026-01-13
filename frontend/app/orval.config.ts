import { defineConfig } from 'orval';

export default defineConfig({
  dataing: {
    input: {
      target: '../dataing/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/lib/api/generated',
      schemas: 'src/lib/api/model',
      client: 'react-query',
      mock: false,
      override: {
        mutator: {
          path: './src/lib/api/client.ts',
          name: 'customInstance',
        },
        query: {
          useQuery: true,
          useMutation: true,
        },
      },
    },
    hooks: {
      afterAllFilesWrite: 'prettier --write',
    },
  },
});
