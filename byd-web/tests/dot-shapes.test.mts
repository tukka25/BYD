import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CYCLE_MS,
  DOTS,
  HOLD_MS,
  MORPH_MS,
  SHAPE_POINTS,
  SHAPES,
  SWEEP,
  dotAt,
  frameAt,
} from "../lib/dot-shapes.ts";

test("every shape has the same dots, inside the frame, left to right", () => {
  for (const name of SHAPES) {
    const points = SHAPE_POINTS[name];
    assert.equal(points.length, DOTS, name);
    for (const p of points) {
      assert.ok(p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1, `${name} point out of frame`);
      assert.ok(p.weight > 0 && p.weight <= 1, `${name} weight`);
    }
    for (let i = 1; i < points.length; i += 1) assert.ok(points[i].x >= points[i - 1].x, `${name} not sorted`);
  }
});

test("the grid lands square in the 5:3 frame", () => {
  const xs = SHAPE_POINTS.grid.map((p) => p.x);
  const ys = SHAPE_POINTS.grid.map((p) => p.y);
  const width = (Math.max(...xs) - Math.min(...xs)) * 5;
  const height = (Math.max(...ys) - Math.min(...ys)) * 3;
  assert.ok(Math.abs(width - height) < 0.01, `${width} x ${height}`);
});

test("the clock holds a shape, then morphs to the next, and wraps around", () => {
  assert.deepEqual(frameAt(0), { from: "line", to: "bars", progress: 0 });
  assert.deepEqual(frameAt(HOLD_MS + MORPH_MS / 2), { from: "line", to: "bars", progress: 0.5 });
  assert.equal(frameAt(CYCLE_MS).from, "bars");
  assert.equal(frameAt(CYCLE_MS * SHAPES.length).from, "line");
  assert.equal(frameAt(-50).progress, 0);
});

test("a dot starts at one shape, ends at the next, and the left ones set off first", () => {
  const a = { x: 0.1, y: 0.2, weight: 0.3 };
  const b = { x: 0.9, y: 0.8, weight: 0.9 };
  assert.deepEqual(dotAt(a, b, 0, 0), a);
  assert.deepEqual(dotAt(a, b, 1, DOTS - 1), b);
  assert.deepEqual(dotAt(a, b, SWEEP, DOTS - 1), a);
  assert.ok(dotAt(a, b, SWEEP, 0).x > a.x);
});
