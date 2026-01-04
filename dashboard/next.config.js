/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: {
    // We run ESLint separately with our custom rules, so disable it during build
    ignoreDuringBuilds: true,
  },
  typescript: {
    // We run type checking separately, but you can disable this too if needed
    // ignoreBuildErrors: true,
  },
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
};

module.exports = nextConfig;
