/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Allow long-running backend requests (avatar generation takes ~2-3 min)
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/static/:path*",
        destination: "http://localhost:8000/static/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
