import { test } from "node:test";
import assert from "node:assert/strict";
import { filterKinds, removeToken, slashTokenAt } from "../lib/slash-menu.ts";

const KINDS = [
  { kind: "bar", label: "Bar chart", best_for: "", needs: "", aliases: ["ranking", "top"] },
  { kind: "treemap", label: "Treemap", best_for: "", needs: "", aliases: ["hierarchy", "nested"] },
  { kind: "kpi", label: "KPI card", best_for: "", needs: "", aliases: ["number", "metric"] },
];

test("a slash at the start or after a space opens the menu", () => {
  assert.deepEqual(slashTokenAt("/tre", 4), { query: "tre", start: 0, end: 4 });
  assert.deepEqual(slashTokenAt("sales by /ba", 12), { query: "ba", start: 9, end: 12 });
  assert.deepEqual(slashTokenAt("/", 1), { query: "", start: 0, end: 1 });
});

test("a slash inside a word does not", () => {
  assert.equal(slashTokenAt("revenue/user", 12), null);
});

test("kinds filter by name first, then by alias", () => {
  assert.deepEqual(filterKinds(KINDS, "tree").map((k) => k.kind), ["treemap"]);
  assert.deepEqual(filterKinds(KINDS, "metric").map((k) => k.kind), ["kpi"]);
  assert.equal(filterKinds(KINDS, "").length, 3);
  assert.deepEqual(filterKinds(KINDS, "zzz"), []);
});

test("picking a kind removes the typed token and puts the caret where it was", () => {
  const token = slashTokenAt("sales by /ba region", 12)!;
  assert.deepEqual(removeToken("sales by /ba region", token), { text: "sales by region", caret: 9 });
});
