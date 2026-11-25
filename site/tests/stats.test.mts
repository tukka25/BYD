import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { findStat, formatStat, type Stat } from "../lib/stats.ts";

const ROOT = new URL("../../", import.meta.url);
const stats: Stat[] = JSON.parse(readFileSync(new URL("../data/stats.json", import.meta.url), "utf8"));
const read = (file: string) => readFileSync(new URL(file, ROOT), "utf8");
const squash = (text: string) => text.replace(/\s+/g, " ");

/* The formatted value must stand on its own in the quote, not as part of a
   longer number: "3" inside "3.3 h" or "1,832" does not count. */
function quotes(quote: string, text: string): boolean {
  const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\d.,])${escaped}(?![\\d]|[.,]\\d)`).test(quote);
}

function at(value: unknown, path: (string | number)[]): unknown {
  return path.reduce<unknown>((node, key) => (node as Record<string | number, unknown> | undefined)?.[key], value);
}

test("percent and counts format as the page shows them", () => {
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }), "94.3%");
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }, 0), "94%");
  assert.equal(formatStat({ value: 1832, format: { kind: "number", decimals: 0 } }), "1,832");
});

test("a value inside a longer number does not count as quoted", () => {
  const quote = "2 epochs, 1,832 steps, 3.3 h";
  assert.equal(quotes(quote, "2"), true);
  assert.equal(quotes(quote, "1,832"), true);
  assert.equal(quotes(quote, "3.3"), true);
  assert.equal(quotes(quote, "3"), false);
  assert.equal(quotes(quote, "1"), false);
  assert.equal(quotes(quote, "32"), false);
});

test("ids are unique and every entry says what it measures", () => {
  assert.equal(new Set(stats.map((stat) => stat.id)).size, stats.length);
  for (const stat of stats) assert.ok(stat.label.length > 10, `${stat.id} needs a label`);
});

test("an unknown id fails loudly", () => {
  assert.throws(() => findStat(stats, "no_such_stat"), /no stat with id no_such_stat/);
});

/* An id the page asks for and the file lacks fails the build (findStat throws).
   The other way round: an entry no component names is a number the page no
   longer shows, and it goes. */
test("every entry is shown somewhere on the page", () => {
  const sources = ["../components/", "../app/"].flatMap((dir) =>
    (readdirSync(new URL(dir, import.meta.url), { recursive: true }) as string[])
      .filter((name) => /\.tsx?$/.test(name))
      .map((name) => readFileSync(new URL(dir + name, import.meta.url), "utf8")),
  );
  const unused = stats.filter((stat) => !sources.some((text) => text.includes(`"${stat.id}"`)));
  assert.deepEqual(
    unused.map((stat) => stat.id),
    [],
  );
});

for (const stat of stats) {
  test(`${stat.id} matches its source`, () => {
    const source = stat.source;
    if (source.kind === "json") {
      assert.equal(at(JSON.parse(read(source.file)), source.path), stat.value);
    } else if (source.kind === "quote") {
      assert.ok(squash(read(source.file)).includes(squash(source.quote)), `${source.file} lacks: ${source.quote}`);
      assert.ok(quotes(source.quote, formatStat(stat)), `the quote does not contain ${formatStat(stat)} on its own`);
    } else {
      const total = source.of.reduce((sum, id) => sum + findStat(stats, id).value, 0);
      assert.ok(Math.abs(total - stat.value) < 1e-9, `${stat.id} is ${stat.value}; its parts add up to ${total}`);
    }
  });
}
