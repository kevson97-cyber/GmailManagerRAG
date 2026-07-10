import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export served by the FastAPI backend (see backend/app/main.py).
  output: "export",
  // Emits out/sync/index.html (not out/sync.html) so Starlette StaticFiles
  // serves hard refreshes of /sync and /assistant correctly.
  trailingSlash: true,
};

export default nextConfig;
