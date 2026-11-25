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

const priceKpi = (number: Record<string, unknown>, title = "Overall Median Nightly Price") => ({
  data: [{ type: "indicator", mode: "number", value: 215, number }],
  layout: { title: { text: title } },
});

test("a currency the model wrote on a KPI gives way to the data's currency", () => {
  assert.equal(at(themed(priceKpi({ prefix: "$", valueformat: ",.2f" }), "GBP").data[0], "number", "prefix"), "£");
});

test("a currency the model wrote is dropped when the data names none", () => {
  const { data } = themed(priceKpi({ prefix: "$", valueformat: ",.2f" }));
  assert.equal(at(data[0], "number", "prefix"), undefined);
  assert.equal(at(data[0], "number", "valueformat"), ",.2f");
});

test("a currency the data names is kept, whatever the model wrote", () => {
  assert.equal(at(themed(priceKpi({ prefix: "$" }, "Total MRR (USD)")).data[0], "number", "prefix"), "$");
  assert.equal(at(themed(priceKpi({ prefix: "€" }, "Total MRR (USD)")).data[0], "number", "prefix"), "$");
});

test("d3's $ flag in a KPI format is a currency mark too", () => {
  const plain = themed(priceKpi({ valueformat: "$,.2f" }));
  assert.equal(at(plain.data[0], "number", "valueformat"), ",.2f");
  assert.equal(at(plain.data[0], "number", "prefix"), undefined);
  assert.equal(at(themed(priceKpi({ valueformat: "$,.2f" }), "EUR").data[0], "number", "prefix"), "€");
});

test("a currency code the model wrote as a suffix goes the same way", () => {
  const { data } = themed(priceKpi({ suffix: " USD" }), "GBP");
  assert.equal(at(data[0], "number", "suffix"), undefined);
  assert.equal(at(data[0], "number", "prefix"), "£");
});

test("a prefix that is not a currency stays", () => {
  assert.equal(at(themed(priceKpi({ prefix: "~" })).data[0], "number", "prefix"), "~");
});

test("a currency tick prefix the model put on an axis gives way to the data's", () => {
  const figure = { data: [bars(3)], layout: { yaxis: { title: { text: "Revenue" }, tickprefix: "$" } } };
  assert.equal(at(themed(figure).layout, "yaxis", "tickprefix"), undefined);
  assert.equal(at(themed(figure, "GBP").layout, "yaxis", "tickprefix"), "£");
});
