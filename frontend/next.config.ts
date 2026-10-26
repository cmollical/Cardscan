import type { NextConfig } from "next";
const backend = process.env.TALLYBINDER_BACKEND_URL || "http://127.0.0.1:8000";
const config: NextConfig = {
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    ...(process.env.TALLYBINDER_DEV_ORIGINS || "").split(",").filter(Boolean),
  ],
  async rewrites() {
    return [
      { source: "/api/backend/:path*", destination: `${backend}/:path*` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(), geolocation=()",
          },
        ],
      },
      {
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: "no-cache" }],
      },
    ];
  },
};
export default config;
