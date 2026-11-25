import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import {
  blockHeight,
  buildLine,
  capitalise,
  changeNote,
  creditTag,
  dataName,
  gridPlacement,
  isIndicator,
  licences,
  ordinal,
  sourceKinds,
  validateDashboard,
  type Dashboard,
} from "../lib/dashboard.ts";
import { DASHBOARD_TITLES } from "../lib/site.ts";

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

test("every committed dashboard has a title and a data loader", () => {
  const loaders = readFileSync(new URL("../components/dashboard-data.ts", import.meta.url), "utf8");
  for (const file of files) {
    const name = file.replace(/\.json$/, "");
    assert.ok(DASHBOARD_TITLES[name], `${name} has no entry in DASHBOARD_TITLES`);
    assert.match(loaders, new RegExp(`^  ${name}: `, "m"), `${name} has no key in DASHBOARD_DATA`);
  }
  assert.deepEqual(Object.keys(DASHBOARD_TITLES).sort(), files.map((f) => f.replace(/\.json$/, "")).sort());
});

const real = (name: string): Dashboard => JSON.parse(readFileSync(new URL(`${name}.json`, DIR), "utf8"));

test("each dashboard's credit is read from its sources: a tag, a name, a change note", () => {
  const airbnb = real("airbnb").sources;
  assert.deepEqual(creditTag(airbnb), { text: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/" });
  assert.deepEqual(airbnb.map(changeNote), ["converted from the CSV", ""]);
  assert.ok(changeNote(airbnb[0]).split(" ").length <= 5);
  assert.equal(dataName(real("airbnb")), "Inside Airbnb");

  // Synthetic data has no licence link: its tag is linked to the script that makes it.
  const shop = real("shop").sources;
  assert.deepEqual(creditTag(shop), { text: "synthetic", url: shop[0].url });
  assert.match(shop[0].url, /make_relational_demo\.py$/);
  assert.deepEqual(shop.map(changeNote), ["", "", "", ""]);
  assert.equal(dataName(real("shop")), "Shop data");

  // CC0 asks for no attribution: no tag.
  assert.equal(creditTag(real("netflix").sources), null);
  assert.equal(dataName(real("netflix")), "Netflix Movies and TV Shows");

  // One source and no licence that needs naming.
  const one = sample();
  one.sources[0].licence_url = "https://creativecommons.org/publicdomain/zero/1.0/";
  assert.equal(creditTag(one.sources), null);
  assert.equal(changeNote(one.sources[0]), "");
  assert.equal(dataName(one), "A test file");
  assert.equal(creditTag([]), null);
  // An Excel file whose note does not say CSV carries no change note.
  assert.equal(changeNote({ name: "a.xlsx", note: "As published." }), "");
});

test("each dashboard names its licence once", () => {
  for (const name of ["airbnb", "shop", "netflix"]) assert.equal(licences(real(name).sources).length, 1, name);
  assert.equal(capitalise(licences(real("shop").sources)[0].licence), "Synthetic, made for this project");
});

test("the line under a prompt says, in words, which try it was and whether every chart was drawn", () => {
  assert.equal(buildLine(real("shop").build), "Sent as typed, the first prompt tried. Every planned chart was drawn.");
  assert.equal(buildLine(real("netflix").build), "Sent as typed, the third prompt tried. Every planned chart was drawn.");
  assert.equal(buildLine(real("airbnb").build), "Sent as typed, the fourth prompt tried. Every planned chart was drawn.");
  assert.equal(
    buildLine({ prompts_tried: 2, charts_planned: 7, charts_drawn: 6 }),
    "Sent as typed, the second prompt tried. 6 of 7 planned charts were drawn.",
  );
  assert.deepEqual(
    [10, 11, 12, 13, 21, 22, 23, 24, 101, 111].map(ordinal),
    ["tenth", "11th", "12th", "13th", "21st", "22nd", "23rd", "24th", "101st", "111th"],
  );
});
