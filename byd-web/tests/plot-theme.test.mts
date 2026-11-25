import { test } from "node:test";
import assert from "node:assert/strict";
import { themed } from "../lib/plot-theme.ts";

function at(value: unknown, ...path: string[]): unknown {
  return path.reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], value);
}

const bars = (n: number) => ({
  type: "bar",
  x: Array.from({ length: n }, (_, i) => `c${i}`),
  y: Array.from({ length: n }, (_, i) => i),
});

test("Plotly's default trace colours become the app's series; a chosen colour stays", () => {
  const { data } = themed({
    data: [
      { ...bars(2), marker: { color: "#636efa" } },
      { ...bars(2), marker: { color: "#123456" } },
    ],
  });
  assert.equal(at(data[0], "marker", "color"), "#176b4e");
  assert.equal(at(data[1], "marker", "color"), "#123456");
});

test("the plot's own title is dropped, since the block header names the chart", () => {
  assert.equal(themed({ data: [], layout: { title: { text: "Sales" } } }).layout.title, undefined);
});

test("a money axis that names its currency gets it, and only that axis", () => {
  const { layout } = themed({
    data: [bars(3)],
    layout: { xaxis: { title: { text: "Year" } }, yaxis: { title: { text: "Revenue (EUR)" } } },
  });
  assert.equal(at(layout, "yaxis", "tickprefix"), "€");
  assert.equal(at(layout, "xaxis", "tickprefix"), undefined);
});

test("an unnamed currency is never invented; the default currency fills a money axis only", () => {
  const price = { data: [bars(3)], layout: { yaxis: { title: { text: "Price" } } } };
  const listings = { data: [bars(3)], layout: { yaxis: { title: { text: "Listings" } } } };
  assert.equal(at(themed(price).layout, "yaxis", "tickprefix"), undefined);
  assert.equal(at(themed(price, "GBP").layout, "yaxis", "tickprefix"), "£");
  assert.equal(at(themed(listings, "GBP").layout, "yaxis", "tickprefix"), undefined);
});

test("a dozen bars or fewer get their values above them; more do not", () => {
  assert.equal(at(themed({ data: [bars(12)] }).data[0], "texttemplate"), "%{y:.5~s}");
  assert.equal(at(themed({ data: [bars(13)] }).data[0], "texttemplate"), undefined);
});

test("a KPI keeps a readable format, replaces a broken one, and takes the named currency", () => {
  const kpi = (valueformat: string) => ({
    data: [{ type: "indicator", mode: "number", value: 583271495.17, number: { valueformat } }],
    layout: { title: { text: "Revenue (USD)" } },
  });
  assert.equal(at(themed(kpi("#1f77b4")).data[0], "number", "valueformat"), ",.0f");
  assert.equal(at(themed(kpi(".1%")).data[0], "number", "valueformat"), ".1%");
  assert.equal(at(themed(kpi("")).data[0], "number", "prefix"), "$");
});
