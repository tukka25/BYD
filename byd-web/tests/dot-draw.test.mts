import { test } from "node:test";
import assert from "node:assert/strict";
import { SHAPE_POINTS } from "../lib/dot-shapes.ts";
import { drawDots, type DotContext } from "../lib/dot-draw.ts";

type Arc = { x: number; y: number; r: number; alpha: number; fill: string };

function recorder() {
  const arcs: Arc[] = [];
  const cleared: number[][] = [];
  const context: DotContext = {
    fillStyle: "",
    globalAlpha: 1,
    clearRect: (x, y, w, h) => {
      cleared.push([x, y, w, h]);
    },
    beginPath: () => {},
    arc: (x, y, r) => {
      arcs.push({ x, y, r, alpha: context.globalAlpha, fill: String(context.fillStyle) });
    },
    fill: () => {},
  };
  return { context, arcs, cleared };
}

const shownIn = (name: keyof typeof SHAPE_POINTS) => SHAPE_POINTS[name].filter((p) => p.weight > 0).length;

test("the first frame clears the canvas and draws the line's dots in the given colour", () => {
  const { context, arcs, cleared } = recorder();
  drawDots(context, { width: 500, height: 300, elapsed: 0, reduced: false, color: "#176b4e" });
  assert.deepEqual(cleared, [[0, 0, 500, 300]]);
  assert.equal(arcs.length, shownIn("line"));
  assert.ok(arcs.every((arc) => arc.fill === "#176b4e"));
  assert.equal(context.globalAlpha, 1);
});

test("every dot sits inside the 8% padding of the frame", () => {
  const { context, arcs } = recorder();
  drawDots(context, { width: 500, height: 300, elapsed: 1234, reduced: false, color: "#000" });
  assert.ok(arcs.length > 0);
  for (const arc of arcs) {
    assert.ok(arc.x >= 40 - 1e-9 && arc.x <= 460 + 1e-9, `x ${arc.x}`);
    assert.ok(arc.y >= 24 - 1e-9 && arc.y <= 276 + 1e-9, `y ${arc.y}`);
  }
});

test("with reduced motion the line holds still, whatever the clock says", () => {
  const first = recorder();
  const later = recorder();
  drawDots(first.context, { width: 320, height: 192, elapsed: 0, reduced: true, color: "#000" });
  drawDots(later.context, { width: 320, height: 192, elapsed: 98_765, reduced: true, color: "#000" });
  assert.deepEqual(first.arcs, later.arcs);
  assert.equal(first.arcs.length, shownIn("line"));
});
