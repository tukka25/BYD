/* The planning loader's geometry: one set of dots laid out as the charts the
   model is choosing between (a line, bars, a grid, a smooth line, an area),
   and the clock that walks the dots from one shape to the next.

   Coordinates are a unit box, y down, drawn into a 5:3 frame; the grid is
   sized for that frame so it lands square. Every shape has the same number of
   points, sorted left to right, so dot i always has somewhere to go and the
   morph sweeps across the frame rather than scrambling.

   Import-free, so `npm test` (Node's own runner) loads it directly. */

export type Point = { x: number; y: number; weight: number };
export type ShapeName = "line" | "bars" | "grid" | "curve" | "area";

export const DOTS = 36;
export const SHAPES: readonly ShapeName[] = ["line", "bars", "grid", "curve", "area"];
export const HOLD_MS = 1500;
export const MORPH_MS = 900;
export const CYCLE_MS = HOLD_MS + MORPH_MS;
/* The last dot starts moving this far into a morph; the first starts at once. */
export const SWEEP = 0.3;

const BASELINE = 0.84;

function byX(points: Point[]): Point[] {
  return [...points].sort((a, b) => a.x - b.x || a.y - b.y);
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

/* A 6 x 6 grid, square in a 5:3 frame, shaded like a small heatmap. */
function grid(): Point[] {
  const points: Point[] = [];
  for (let column = 0; column < 6; column += 1) {
    for (let row = 0; row < 6; row += 1) {
      const heat = Math.min(1, (column + 5 - row) / 12 + ((column * 7 + row * 3) % 5) / 25);
      points.push({ x: 0.35 + column * 0.06, y: 0.22 + row * 0.1, weight: 0.25 + 0.75 * heat });
    }
  }
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
  grid: grid(),
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
