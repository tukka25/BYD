import type { Dashboard } from "@/lib/dashboard";

/* Each dashboard file becomes its own chunk, fetched when one of its charts
   first nears the screen, so the figures stay out of the page's first load.
   The cards themselves are in the HTML from the build. */
export const DASHBOARD_DATA: Record<string, () => Promise<Dashboard>> = {
  airbnb: () => import("@/data/dashboards/airbnb.json").then((mod) => mod.default as unknown as Dashboard),
  shop: () => import("@/data/dashboards/shop.json").then((mod) => mod.default as unknown as Dashboard),
  netflix: () => import("@/data/dashboards/netflix.json").then((mod) => mod.default as unknown as Dashboard),
};
