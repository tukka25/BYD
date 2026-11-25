import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ROOT = new URL("../../", import.meta.url);
const loss = JSON.parse(readFileSync(new URL("../data/loss.json", import.meta.url), "utf8"));
const squash = (text: string) => text.replace(/\s+/g, " ");

test("lora-v1's validation losses are the ones its run recorded", () => {
  const readme = squash(readFileSync(new URL(loss.v1.source.file, ROOT), "utf8"));
  assert.ok(readme.includes(loss.v1.source.quote));
  assert.deepEqual(loss.v1.points, (loss.v1.source.quote.match(/\d+\.\d+/g) ?? []).map(Number));
});

test("lora-v2's validation losses are the trainer's own log, to four places", () => {
  const state = JSON.parse(readFileSync(new URL(loss.v2.source.file, ROOT), "utf8"));
  const evals = state.log_history.filter((entry: { eval_loss?: number }) => entry.eval_loss !== undefined);
  assert.deepEqual(loss.v2.steps, evals.map((entry: { step: number }) => entry.step));
  assert.deepEqual(
    loss.v2.points,
    evals.map((entry: { eval_loss: number }) => Math.round(entry.eval_loss * 1e4) / 1e4),
  );
});
