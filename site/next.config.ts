import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // A static site: everything the page shows is in the build (site/data/).
  output: "export",
  // site/ is one project inside a larger repository, like byd-web. Pin the
  // workspace root here, or Turbopack walks up to the git root and resolves
  // dependencies from a node_modules that does not exist there.
  turbopack: {
    root: projectDir,
  },
  outputFileTracingRoot: projectDir,
};

export default nextConfig;
