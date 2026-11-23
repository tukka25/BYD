/* The planning loader's geometry: one set of dots laid out as every kind of
   chart the model can draw, and the clock that walks the dots from one shape
   to the next.

   Coordinates are a unit box, y down, drawn into a 5:3 frame; anything meant
   to be square or round is sized for that frame (a circle's x radius is 3/5
   of its y radius). Every shape has the same number of points, sorted left to
   right, so dot i always has somewhere to go and a morph sweeps across the
   frame rather than scrambling. A shape that needs fewer dots parks the rest
   at weight 0: they fade out where it starts and back in where the next needs
   them.

   Import-free, so `npm test` (Node's own runner) loads it directly. */

export type Point = { x: number; y: number; weight: number };
export type ShapeName =
  | "line"
  | "bars"
  | "pie"
  | "scatter"
  | "heatmap"
  | "funnel"
  | "box"
  | "treemap"
  | "sunburst"
  | "waterfall"
  | "kpi"
  | "histogram"
  | "curve"
  | "area";

export const DOTS = 36;
/* Ordered so each shape is unlike the one before it, which makes every morph
   travel; the smooth line hands over to the area it fills. */
export const SHAPES: readonly ShapeName[] = [
  "line",
  "bars",
  "pie",
  "scatter",
  "heatmap",
  "funnel",
  "box",
  "treemap",
  "sunburst",
  "waterfall",
  "kpi",
  "histogram",
  "curve",
  "area",
];
/* The shape that stands for each kind in the "/" menu (lib/chart-kinds.ts). */
export const SHAPE_FOR_KIND: Readonly<Record<string, ShapeName>> = {
  kpi: "kpi",
  bar: "bars",
  line: "curve",
  area: "area",
  scatter: "scatter",
  pie: "pie",
  histogram: "histogram",
  box: "box",
  heatmap: "heatmap",
  treemap: "treemap",
  sunburst: "sunburst",
  funnel: "funnel",
  waterfall: "waterfall",
};
export const HOLD_MS = 1500;
export const MORPH_MS = 900;
export const CYCLE_MS = HOLD_MS + MORPH_MS;
/* The last dot starts moving this far into a morph; the first starts at once. */
export const SWEEP = 0.3;
/* A circle's x radius per unit of y radius, in the 5:3 frame. */
const ROUND = 3 / 5;
const BASELINE = 0.84;

function byX(points: Point[]): Point[] {
  if (points.length !== DOTS) throw new Error(`a shape needs ${DOTS} dots, got ${points.length}`);
  return [...points].sort((a, b) => a.x - b.x || a.y - b.y);
}

/* Dots a shape does not need, parked invisibly at one of its own points. */
function park(points: Point[], at: { x: number; y: number }): Point[] {
  const parked = [...points];
  while (parked.length < DOTS) parked.push({ x: at.x, y: at.y, weight: 0 });
  return parked;
}

/* A zigzag through six nodes, like the line in the logo: the nodes are heavy,
   the dots between them light. */
function line(): Point[] {
  const nodes = [
    [0.06, 0.74],
    [0.24, 0.52],
    [0.4, 0.6],
    [0.58, 0.32],
    [0.76, 0.42],
    [0.94, 0.2],
  ];
  const lengths = nodes.slice(1).map(([x, y], i) => Math.hypot(x - nodes[i][0], y - nodes[i][1]));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  const between = DOTS - nodes.length;
  const shares = lengths.map((length) => Math.floor((between * length) / total));
  for (let i = 0; shares.reduce((a, b) => a + b, 0) < between; i += 1) shares[i % shares.length] += 1;

  const points: Point[] = nodes.map(([x, y]) => ({ x, y, weight: 1 }));
  shares.forEach((count, segment) => {
    const [x0, y0] = nodes[segment];
    const [x1, y1] = nodes[segment + 1];
    for (let k = 1; k <= count; k += 1) {
      const t = k / (count + 1);
      points.push({ x: x0 + (x1 - x0) * t, y: y0 + (y1 - y0) * t, weight: 0.35 });
    }
  });
  return byX(points);
}

/* Five bars, each two dots wide; the top dot of each column is heavier. */
function bars(): Point[] {
  const heights = [3, 4, 3, 5, 3];
  const centres = [0.18, 0.34, 0.5, 0.66, 0.82];
  const points: Point[] = [];
  heights.forEach((rows, bar) => {
    for (const dx of [-0.03, 0.03]) {
      for (let row = 0; row < rows; row += 1) {
        points.push({ x: centres[bar] + dx, y: BASELINE - row * 0.13, weight: row === rows - 1 ? 0.85 : 0.45 });
      }
    }
  });
  return byX(points);
}

/* A donut in three slices: 16, 11 and 9 dots, a gap between slices, each
   slice a shade lighter than the last. */
function pie(): Point[] {
  const slices = [16, 11, 9];
  const shades = [0.95, 0.6, 0.32];
  const step = 8.6;
  const gap = (360 - step * (DOTS - slices.length)) / slices.length;
  const ry = 0.36;
  const points: Point[] = [];
  let angle = -90;
  slices.forEach((count, slice) => {
    for (let k = 0; k < count; k += 1) {
      const radians = (angle * Math.PI) / 180;
      points.push({ x: 0.5 + ry * ROUND * Math.cos(radians), y: 0.5 + ry * Math.sin(radians), weight: shades[slice] });
      angle += k === count - 1 ? gap : step;
    }
  });
  return byX(points);
}

/* A cloud with a trend in it: fixed noise, so it lands the same every time. */
function scatter(): Point[] {
  let seed = 7;
  const random = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  const clamp = (value: number) => Math.min(0.92, Math.max(0.08, value));
  return byX(
    Array.from({ length: DOTS }, (_, i) => {
      const along = i / (DOTS - 1);
      return {
        x: clamp(0.08 + 0.84 * along + (random() - 0.5) * 0.05),
        y: clamp(0.74 - 0.48 * along + (random() - 0.5) * 0.26),
        weight: 0.35 + 0.55 * random(),
      };
    }),
  );
}

/* A 6 x 6 grid, square in a 5:3 frame, shaded like a small heatmap. */
function heatmap(): Point[] {
  const points: Point[] = [];
  for (let column = 0; column < 6; column += 1) {
    for (let row = 0; row < 6; row += 1) {
      const heat = Math.min(1, (column + 5 - row) / 12 + ((column * 7 + row * 3) % 5) / 25);
      points.push({ x: 0.35 + column * 0.06, y: 0.22 + row * 0.1, weight: 0.25 + 0.75 * heat });
    }
  }
  return byX(points);
}

/* Five stages, centred, each narrower and lighter than the one above. */
function funnel(): Point[] {
  const stages = [10, 8, 7, 6, 5];
  const shades = [0.95, 0.8, 0.65, 0.5, 0.38];
  const points: Point[] = [];
  stages.forEach((count, stage) => {
    for (let k = 0; k < count; k += 1) {
      points.push({ x: 0.5 - (count - 1) * 0.03 + k * 0.06, y: 0.2 + stage * 0.15, weight: shades[stage] });
    }
  });
  return byX(points);
}

/* Two box plots: the box's top, median and bottom rows and its sides, a
   whisker above and below, and one outlier each. The median is the heaviest. */
function box(): Point[] {
  const boxes = [
    { cx: 0.36, top: 0.36, median: 0.5, bottom: 0.64, outlier: 0.9 },
    { cx: 0.64, top: 0.28, median: 0.4, bottom: 0.56, outlier: 0.06 },
  ];
  const points: Point[] = [];
  for (const { cx, top, median, bottom, outlier } of boxes) {
    for (const dx of [-0.06, 0, 0.06]) {
      points.push({ x: cx + dx, y: top, weight: 0.6 });
      points.push({ x: cx + dx, y: median, weight: 1 });
      points.push({ x: cx + dx, y: bottom, weight: 0.6 });
    }
    for (const dx of [-0.06, 0.06]) {
      points.push({ x: cx + dx, y: (top + median) / 2, weight: 0.6 });
      points.push({ x: cx + dx, y: (median + bottom) / 2, weight: 0.6 });
    }
    for (const dy of [0.07, 0.14]) {
      points.push({ x: cx, y: top - dy, weight: 0.45 });
      points.push({ x: cx, y: bottom + dy, weight: 0.45 });
    }
    points.push({ x: cx, y: outlier, weight: 0.75 });
  }
  return byX(points);
}

/* Five tiles on one grid of square cells, an empty row or column between
   them, each tile a shade of its own. 32 dots; the other four are parked. */
function treemap(): Point[] {
  const step = { x: 0.066, y: 0.11 };
  const origin = { x: 0.5 - 3.5 * step.x, y: 0.5 - 2.5 * step.y };
  const tiles = [
    { columns: [0, 2], rows: [0, 3], weight: 0.95 },
    { columns: [0, 2], rows: [5, 5], weight: 0.5 },
    { columns: [4, 7], rows: [0, 1], weight: 0.8 },
    { columns: [4, 5], rows: [3, 5], weight: 0.6 },
    { columns: [7, 7], rows: [3, 5], weight: 0.35 },
  ];
  const points: Point[] = [];
  for (const { columns, rows, weight } of tiles) {
    for (let column = columns[0]; column <= columns[1]; column += 1) {
      for (let row = rows[0]; row <= rows[1]; row += 1) {
        points.push({ x: origin.x + column * step.x, y: origin.y + row * step.y, weight });
      }
    }
  }
  return byX(park(points, { x: origin.x + step.x, y: origin.y + 1.5 * step.y }));
}

/* A centre, an inner ring of 11 and an outer ring of 24, in shaded segments. */
function sunburst(): Point[] {
  const ring = (count: number, ry: number, shade: (k: number) => number): Point[] =>
    Array.from({ length: count }, (_, k) => {
      const radians = ((-90 + (360 * k) / count) * Math.PI) / 180;
      return { x: 0.5 + ry * ROUND * Math.cos(radians), y: 0.5 + ry * Math.sin(radians), weight: shade(k) };
    });
  return byX([
    { x: 0.5, y: 0.5, weight: 1 },
    ...ring(11, 0.17, (k) => (k < 6 ? 0.85 : 0.55)),
    ...ring(24, 0.36, (k) => (k < 9 ? 0.85 : k < 15 ? 0.6 : k < 20 ? 0.72 : 0.4)),
  ]);
}

/* Steps up and down to a total: each bar two dots wide, starting where the
   last ended; rises are heavier than falls, and the total heaviest. */
function waterfall(): Point[] {
  const steps = [
    { from: 0, rows: 4, weight: 0.8 },
    { from: 4, rows: 3, weight: 0.8 },
    { from: 6, rows: 1, weight: 0.45 },
    { from: 6, rows: 2, weight: 0.8 },
    { from: 7, rows: 1, weight: 0.45 },
    { from: 0, rows: 7, weight: 0.95 },
  ];
  const centres = [0.14, 0.29, 0.43, 0.57, 0.71, 0.86];
  const points: Point[] = [];
  steps.forEach(({ from, rows, weight }, bar) => {
    for (const dx of [-0.022, 0.022]) {
      for (let row = from; row < from + rows; row += 1) {
        points.push({ x: centres[bar] + dx, y: 0.86 - row * 0.085, weight });
      }
    }
  });
  return byX(points);
}

/* A KPI as a gauge: a half ring of 28 dots, heavy up to the value, and a
   needle of 8 pointing at it. */
function kpi(): Point[] {
  const centre = { x: 0.5, y: 0.78 };
  const ry = 0.56;
  const value = 0.6;
  const points: Point[] = [];
  for (let k = 0; k < 28; k += 1) {
    const share = k / 27;
    const radians = Math.PI + share * Math.PI;
    points.push({
      x: centre.x + ry * ROUND * Math.cos(radians),
      y: centre.y + ry * Math.sin(radians),
      weight: share <= value ? 0.95 : 0.3,
    });
  }
  const needle = Math.PI + value * Math.PI;
  for (let k = 0; k < 8; k += 1) {
    const reach = 0.08 + (0.64 * k) / 7;
    points.push({
      x: centre.x + ry * reach * ROUND * Math.cos(needle),
      y: centre.y + ry * reach * Math.sin(needle),
      weight: k === 7 ? 1 : 0.8,
    });
  }
  return byX(points);
}

/* Nine touching columns of one dot, rising to a peak and falling away. */
function histogram(): Point[] {
  const heights = [1, 2, 4, 6, 7, 6, 5, 3, 2];
  const points: Point[] = [];
  heights.forEach((rows, column) => {
    for (let row = 0; row < rows; row += 1) {
      points.push({ x: 0.18 + column * 0.08, y: BASELINE - row * 0.09, weight: row === rows - 1 ? 0.9 : 0.5 });
    }
  });
  return byX(points);
}

/* The smooth line: a rising wave. */
function curveAt(x: number): number {
  const t = (x - 0.06) / 0.88;
  return 0.62 - 0.22 * Math.sin(Math.PI * 1.5 * t) - 0.12 * t;
}

function curve(): Point[] {
  return byX(
    Array.from({ length: DOTS }, (_, k) => {
      const x = 0.06 + (0.88 * k) / (DOTS - 1);
      return { x, y: curveAt(x), weight: k % 7 === 0 ? 0.9 : 0.4 };
    }),
  );
}

/* The same wave, filled to the baseline: each column's top dot traces it. */
function area(): Point[] {
  const heights = [2, 3, 4, 5, 6, 5, 4, 4, 3];
  const points: Point[] = [];
  heights.forEach((count, column) => {
    const x = 0.1 + column * 0.1;
    const top = curveAt(x);
    for (let d = 0; d < count; d += 1) {
      const y = count === 1 ? top : BASELINE - (d * (BASELINE - top)) / (count - 1);
      points.push({ x, y, weight: d === count - 1 ? 0.9 : 0.3 });
    }
  });
  return byX(points);
}

export const SHAPE_POINTS: Readonly<Record<ShapeName, readonly Point[]>> = {
  line: line(),
  bars: bars(),
  pie: pie(),
  scatter: scatter(),
  heatmap: heatmap(),
  funnel: funnel(),
  box: box(),
  treemap: treemap(),
  sunburst: sunburst(),
  waterfall: waterfall(),
  kpi: kpi(),
  histogram: histogram(),
  curve: curve(),
  area: area(),
};

/* Where the clock is: the shape it holds or leaves, the shape it is heading
   for, and how far through the morph it is (0 while holding). */
export function frameAt(ms: number): { from: ShapeName; to: ShapeName; progress: number } {
  const elapsed = Math.max(0, ms);
  const cycle = Math.floor(elapsed / CYCLE_MS);
  const within = elapsed - cycle * CYCLE_MS;
  const from = SHAPES[cycle % SHAPES.length];
  const to = SHAPES[(cycle + 1) % SHAPES.length];
  return { from, to, progress: within <= HOLD_MS ? 0 : (within - HOLD_MS) / MORPH_MS };
}

export function easeOut(t: number): number {
  return 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 4);
}

/* Dot `index` of `count`, part way from `a` to `b`. Dots on the left set off
   first, so a morph sweeps across the frame. */
export function dotAt(a: Point, b: Point, progress: number, index: number, count = DOTS): Point {
  const delay = count > 1 ? (SWEEP * index) / (count - 1) : 0;
  const local = easeOut((progress - delay) / (1 - delay));
  if (local <= 0) return { ...a };
  if (local >= 1) return { ...b };
  return {
    x: a.x + (b.x - a.x) * local,
    y: a.y + (b.y - a.y) * local,
    weight: a.weight + (b.weight - a.weight) * local,
  };
}
