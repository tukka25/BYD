import { test } from "node:test";
import assert from "node:assert/strict";
import { missingKindsNotice } from "../lib/kind-notice.ts";

const KINDS = [
  { kind: "pie", label: "Pie chart" },
  { kind: "area", label: "Area chart" },
  { kind: "kpi", label: "KPI card" },
  { kind: "funnel", label: "Funnel" },
];

test("one missing kind is one plain sentence", () => {
  assert.equal(missingKindsNotice(["pie"], KINDS), "Could not plan a pie chart for this data.");
});

test("articles and acronyms read right", () => {
  assert.equal(missingKindsNotice(["area"], KINDS), "Could not plan an area chart for this data.");
  assert.equal(missingKindsNotice(["kpi"], KINDS), "Could not plan a KPI card for this data.");
});

test("several missing kinds share the one line", () => {
  assert.equal(
    missingKindsNotice(["pie", "funnel", "kpi"], KINDS),
    "Could not plan a pie chart, a funnel or a KPI card for this data.",
  );
});

test("nothing missing, nothing to say", () => {
  assert.equal(missingKindsNotice([], KINDS), "");
});
