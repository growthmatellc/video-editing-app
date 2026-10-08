import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The ffmpeg binary and caption font are required by the Video Edit routes
  // and are not imported as JS, so the file tracer will not see them.
  serverExternalPackages: ["ffmpeg-static"],
  outputFileTracingIncludes: {
    "/api/projects/**": ["./node_modules/ffmpeg-static/**/*", "./assets/fonts/**/*"],
  },
  experimental: {
    // Local uploads of short talking-head clips go through the route handler.
    // Vercel still caps request bodies (~4.5MB); larger files use Blob client upload.
    proxyClientMaxBodySize: "512mb",
  },
};

export default nextConfig;
