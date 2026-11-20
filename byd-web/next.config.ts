import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // Pin the workspace root to this directory.
  //
  // byd-web is one project inside a larger repository, and its package.json and
  // package-lock.json live here rather than at the repository root. Turbopack
  // otherwise walks up and picks the git root as the workspace root, then tries
  // to resolve dependencies from a node_modules directory that does not exist
  // there. The failure is not obvious from the symptom: `next dev` reports
  // "Ready", binds port 3000, and only fails when a request arrives, with
  // `resolve 'tailwindcss' in '<repo root>'`.
  turbopack: {
    root: projectDir,
  },
  outputFileTracingRoot: projectDir,
};

export default nextConfig;
