import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { findStat, formatStat, type Stat } from "../lib/stats.ts";

const ROOT = new URL("../../", import.meta.url);
const stats: Stat[] = JSON.parse(readFileSync(new URL("../data/stats.json", import.meta.url), "utf8"));
const read = (file: string) => readFileSync(new URL(file, ROOT), "utf8");
const squash = (text: string) => text.replace(/\s+/g, " ");

function at(value: unknown, path: (string | number)[]): unknown {
  return path.reduce<unknown>((node, key) => (node as Record<string | number, unknown> | undefined)?.[key], value);
}

test("percent, money, counts and durations format as the page shows them", () => {
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }), "94.3%");
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }, 0), "94%");
  assert.equal(formatStat({ value: 34.85, format: { kind: "usd", decimals: 0 } }), "$35");
  assert.equal(formatStat({ value: 5.4708, format: { kind: "usd", decimals: 4 } }, 2), "$5.47");
  assert.equal(formatStat({ value: 1832, format: { kind: "number", decimals: 0 } }), "1,832");
  assert.equal(formatStat({ value: 8668, format: { kind: "duration" } }), "2 h 24 m");
});

test("ids are unique and every entry says what it measures", () => {
  assert.equal(new Set(stats.map((stat) => stat.id)).size, stats.length);
  for (const stat of stats) assert.ok(stat.label.length > 10, `${stat.id} needs a label`);
});

test("an unknown id fails loudly", () => {
  assert.throws(() => findStat(stats, "no_such_stat"), /no stat with id no_such_stat/);
});

for (const stat of stats) {
  test(`${stat.id} matches its source`, () => {
    const source = stat.source;
    if (source.kind === "json") {
      assert.equal(at(JSON.parse(read(source.file)), source.path), stat.value);
    } else if (source.kind === "quote") {
      assert.ok(squash(read(source.file)).includes(squash(source.quote)), `${source.file} lacks: ${source.quote}`);
      assert.ok(source.quote.includes(formatStat(stat)), `the quote does not contain ${formatStat(stat)}`);
    } else {
      const total = source.of.reduce((sum, id) => sum + findStat(stats, id).value, 0);
      assert.ok(Math.abs(total - stat.value) < 1e-9, `${stat.id} is ${stat.value}; its parts add up to ${total}`);
    }
  });
}
