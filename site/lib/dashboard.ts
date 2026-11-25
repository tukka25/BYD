/* The dashboard files the page shows (data/dashboards/*.json, written by
   backend/scripts/make_showcase.py), and where their blocks sit. Import-free,
   so Node's test runner can load it. */

export type BlockKind = "text" | "chart" | "metric";

export type DashboardBlock = {
  kind: BlockKind;
  title: string;
  chart_type: string | null;
  figure: { data?: unknown[]; layout?: Record<string, unknown> } | null;
  text_body: string | null;
  code: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type DashboardSource = {
  name: string;
  kind: "file" | "database";
  rows: number;
  url: string;
  licence: string;
  licence_url: string;
  note: string;
};

export type Dashboard = {
  name: string;
  title: string;
  prompt: string;
  currency: string;
  sources: DashboardSource[];
  blocks: DashboardBlock[];
  build: {
    charts_planned: number;
    charts_drawn: number;
    skipped: { label: string; reason: string }[];
    missing_kinds: string[];
    seconds: number;
    prompts_tried: number;
  };
  model: { base: string; adapter: string; label: string };
  app_commit: string;
  generated_at: string;
};

export const COLUMNS = 12;
export const ROW_HEIGHT = 44; // the canvas's react-grid-layout rowHeight (report-canvas.tsx)
export const GAP = 16; // and its margin
export const MAX_BYTES = 1_500_000;

/** Where a block sits in the 12-column grid: the app's saved x, y, w and h. */
export function gridPlacement(block: Pick<DashboardBlock, "x" | "y" | "w" | "h">) {
  return { gridColumn: `${block.x + 1} / span ${block.w}`, gridRow: `${block.y + 1} / span ${block.h}` };
}

/** A block's height in pixels, as the canvas draws it: h rows and the gaps between them. */
export function blockHeight(h: number): number {
  return h * ROW_HEIGHT + (h - 1) * GAP;
}

/** An all-indicator figure is a stat card, drawn without plot chrome, as in the app. */
export function isIndicator(block: Pick<DashboardBlock, "figure">): boolean {
  const data = (block.figure?.data ?? []) as Array<{ type?: string }>;
  return data.length > 0 && data.every((trace) => trace?.type === "indicator");
}

/** "Excel + CSV", "Postgres", "CSV": what a dashboard was built from. */
export function sourceKinds(dashboard: Pick<Dashboard, "sources">): string {
  const kinds = dashboard.sources.map((source) => {
    if (source.kind === "database") return "Postgres";
    return /\.xlsx?$/i.test(source.name) ? "Excel" : "CSV";
  });
  return [...new Set(kinds)].join(" + ");
}

/** What is wrong with a dashboard file, in words. Empty when it is fit to show. */
export function validateDashboard(value: unknown, bytes: number): string[] {
  if (!value || typeof value !== "object") return ["not a JSON object"];
  const d = value as Partial<Dashboard>;
  const problems: string[] = [];
  if (bytes >= MAX_BYTES) problems.push(`${bytes} bytes, at or over ${MAX_BYTES} bytes`);
  for (const key of ["name", "title", "prompt", "app_commit", "generated_at"] as const) {
    if (typeof d[key] !== "string" || !d[key]) problems.push(`no ${key}`);
  }
  if (typeof d.currency !== "string") problems.push("no currency (an empty string when the source names none)");
  if (!Array.isArray(d.sources) || d.sources.length === 0) problems.push("no sources");
  for (const source of d.sources ?? []) {
    for (const key of ["name", "url", "licence", "note"] as const) {
      if (!source[key]) problems.push(`source ${source.name || "?"} has no ${key}`);
    }
    if (!(source.rows > 0)) problems.push(`source ${source.name} has no row count`);
    if (source.kind !== "file" && source.kind !== "database") problems.push(`source ${source.name} is a ${source.kind}`);
  }
  if (!Array.isArray(d.blocks) || d.blocks.length === 0) problems.push("no blocks");
  for (const block of d.blocks ?? []) {
    const name = block.title || "an untitled block";
    if (!["text", "chart", "metric"].includes(block.kind)) problems.push(`${name}: kind ${block.kind}`);
    if (block.kind === "text" && !block.text_body) problems.push(`${name}: a note with no text`);
    if (block.kind !== "text" && !Array.isArray(block.figure?.data)) problems.push(`${name}: no figure`);
    const inside = block.x >= 0 && block.y >= 0 && block.w >= 1 && block.h >= 1 && block.x + block.w <= COLUMNS;
    if (!inside) problems.push(`${name}: outside the 12-column grid`);
  }
  if (!d.build) {
    problems.push("no build record");
  } else {
    const drawn = (d.blocks ?? []).filter((block) => block.kind !== "text").length;
    if (d.build.charts_drawn !== drawn) {
      problems.push(`build says ${d.build.charts_drawn} charts drawn; the file holds ${drawn}`);
    }
    if (!(d.build.prompts_tried >= 1)) problems.push("build.prompts_tried is under 1");
  }
  if (!d.model?.label) problems.push("no model label");
  return problems;
}
