import type { KindOption } from "@/lib/slash-menu";

export type ChartKind = KindOption;

export interface KindExample {
  kind: string;
  title: string;
  figure: Record<string, unknown>;
}

/* The kinds the model can draw. A fixed set, so it lives here and nothing
   fetches it: the "/" menu and the chart kinds panel both read this constant.
   Same kinds, same order and same labels as planning_contract.CHART_KINDS and
   agents/chart_kinds.KIND_INFO in the backend, and
   backend/tests/test_chart_kinds_frontend.py reads this file as text and fails
   if they differ, so the UI can never offer a kind the planner rejects. Keep
   `label` right after `kind` in every entry: that test reads the pair as text. */
export const CHART_KINDS: ChartKind[] = [
  { kind: "kpi", label: "KPI card", best_for: "One headline number", needs: "a measure",
    aliases: ["number", "metric", "indicator", "card"] },
  { kind: "bar", label: "Bar chart", best_for: "Comparing groups, or a top 10", needs: "a category and a measure",
    aliases: ["column", "ranking", "top"] },
  { kind: "line", label: "Line chart", best_for: "A trend over time", needs: "a date or year and a measure",
    aliases: ["trend", "timeline"] },
  { kind: "area", label: "Area chart", best_for: "A total building up over time",
    needs: "a date or year and a measure", aliases: ["stacked", "cumulative"] },
  { kind: "scatter", label: "Scatter plot", best_for: "How two measures relate", needs: "two measures",
    aliases: ["correlation", "relationship", "dots"] },
  { kind: "pie", label: "Pie chart", best_for: "Shares of a whole, few slices", needs: "a category and a measure",
    aliases: ["donut", "share"] },
  { kind: "histogram", label: "Histogram", best_for: "How one measure is spread", needs: "one measure",
    aliases: ["distribution", "spread"] },
  { kind: "box", label: "Box plot", best_for: "Spread and outliers by group",
    needs: "a measure, optionally a category", aliases: ["boxplot", "outliers"] },
  { kind: "heatmap", label: "Heatmap", best_for: "Two groupings at once",
    needs: "two categories or dates and a measure", aliases: ["matrix", "grid"] },
  { kind: "treemap", label: "Treemap", best_for: "Parts of a whole, nested",
    needs: "one or two categories and a measure", aliases: ["hierarchy", "nested"] },
  { kind: "sunburst", label: "Sunburst", best_for: "A hierarchy in rings", needs: "two categories and a measure",
    aliases: ["rings", "radial"] },
  { kind: "funnel", label: "Funnel", best_for: "Drop-off between stages", needs: "a stage category and a measure",
    aliases: ["conversion", "stages"] },
  { kind: "waterfall", label: "Waterfall", best_for: "How a total is built up step by step",
    needs: "a category or period and amounts", aliases: ["bridge", "contribution"] },
];

/** Charts the model drew, one per kind it managed; a kind it did not draw has
    none. A file that does not load throws, naming the HTTP status, so the
    panel can say so: an empty result would read as "No example yet" for every
    kind, which would be false. */
export async function loadKindExamples(): Promise<Record<string, KindExample>> {
  const response = await fetch("/chart-kinds/examples.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const examples = (await response.json()) as KindExample[];
  return Object.fromEntries(examples.map((example) => [example.kind, example]));
}
