import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://dataing.io',
  output: 'static',
  build: {
    assets: '_assets'
  }
});
