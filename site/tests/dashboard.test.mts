import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import {
  blockHeight,
  gridPlacement,
  isIndicator,
  sourceKinds,
  validateDashboard,
  type Dashboard,
} from "../lib/dashboard.ts";

function sample(): Dashboard {
  return {
    name: "sample",
    title: "Sample",
    prompt: "show me sales",
    currency: "",
    sources: [
      { name: "sales.csv", kind: "file", rows: 10, url: "https://example.org/sales.csv", licence: "CC0 1.0",
        licence_url: "", note: "A test file." },
    ],
    blocks: [
      { kind: "text", title: "About this data", chart_type: null, figure: null, text_body: "<p>Ten rows.</p>",
        code: null, x: 0, y: 0, w: 12, h: 3 },
      { kind: "chart", title: "Sales by month", chart_type: "line", figure: { data: [{ type: "scatter" }] },
        text_body: null, code: "fig = px.line(df)", x: 0, y: 3, w: 8, h: 8 },
      { kind: "metric", title: "Total sales", chart_type: "kpi", figure: { data: [{ type: "indicator" }] },
        text_body: null, code: "fig = go.Figure()", x: 8, y: 3, w: 4, h: 3 },
    ],
    build: { charts_planned: 2, charts_drawn: 2, skipped: [], missing_kinds: [], seconds: 60, prompts_tried: 1 },
    model: { base: "models/qwen3.5-9b-4bit", adapter: "runs/adapters-mlx-v2", label: "lora-v2" },
    app_commit: "abc1234",
    generated_at: "2026-11-26T09:30:00Z",
  };
}

const problems = (dashboard: Dashboard, bytes = 1000) => validateDashboard(dashboard, bytes).join("; ");

test("a well-formed dashboard has no problems", () => {
  assert.equal(problems(sample()), "");
});

test("a broken file is refused, in words", () => {
  const overflow = sample();
  overflow.blocks[2].w = 5;
  assert.match(problems(overflow), /Total sales: outside the 12-column grid/);

  const empty = sample();
  empty.blocks[1].figure = null;
  assert.match(problems(empty), /Sales by month: no figure/);

  const miscounted = sample();
  miscounted.build.charts_drawn = 3;
  assert.match(problems(miscounted), /build says 3 charts drawn; the file holds 2/);

  const unsourced = sample();
  unsourced.sources[0].licence = "";
  assert.match(problems(unsourced), /source sales.csv has no licence/);

  assert.match(problems(sample(), 1_500_000), /at or over 1500000 bytes/);
});

test("blocks sit where the app saved them, at the canvas's row height and gap", () => {
  assert.deepEqual(gridPlacement({ x: 8, y: 3, w: 4, h: 3 }), { gridColumn: "9 / span 4", gridRow: "4 / span 3" });
  assert.equal(blockHeight(8), 8 * 44 + 7 * 16);
});

test("an all-indicator figure is a stat card", () => {
  const [, chart, metric] = sample().blocks;
  assert.equal(isIndicator(metric), true);
  assert.equal(isIndicator(chart), false);
});

test("a tab names the kinds of source behind its dashboard", () => {
  const file = sample().sources[0];
  assert.equal(sourceKinds({ sources: [{ ...file, name: "listings.xlsx" }, file] }), "Excel + CSV");
  assert.equal(sourceKinds({ sources: [{ ...file, kind: "database", name: "spotify.tracks" }] }), "Postgres");
});

const DIR = new URL("../data/dashboards/", import.meta.url);
const files = readdirSync(DIR).filter((name) => name.endsWith(".json"));

test("three dashboards are on the page, each drawn by lora-v2", () => {
  assert.equal(files.length, 3, files.join(", "));
  for (const name of files) {
    assert.equal(JSON.parse(readFileSync(new URL(name, DIR), "utf8")).model.label, "lora-v2", name);
  }
});

for (const name of files) {
  test(`${name} is fit to show`, () => {
    const path = new URL(name, DIR);
    assert.deepEqual(validateDashboard(JSON.parse(readFileSync(path, "utf8")), statSync(path).size), []);
  });
}
