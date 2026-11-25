import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/* The hero animation, the chart re-theme and the note sanitiser are the app's
   own code, not lookalikes: each file here must be byte-identical to its
   byd-web original. Change the original, then run `npm run sync-lib`. */
const COPIES = ["dot-shapes.ts", "dot-draw.ts", "plot-theme.ts", "rich-text.ts"];

for (const name of COPIES) {
  test(`lib/${name} is byte-identical to byd-web/lib/${name}`, () => {
    const copy = readFileSync(new URL(`../lib/${name}`, import.meta.url));
    const original = readFileSync(new URL(`../../byd-web/lib/${name}`, import.meta.url));
    assert.ok(copy.equals(original), `site/lib/${name} differs from byd-web/lib/${name}: run npm run sync-lib`);
  });
}
