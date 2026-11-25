import { DOTS, SHAPE_POINTS, dotAt, frameAt, type ShapeName } from "./dot-shapes.ts";

/* The dot animation on a canvas: the build loader's (components/build-loader.tsx)
   and, through a byte-identical copy, the landing page's hero
   (site/lib/dot-draw.ts, checked by site/tests/copies.test.mts).

   drawDots draws one frame and touches only the context it is given, so a
   test can run it without a browser. animateDots owns the canvas: it sizes it
   for the device pixel ratio, draws the first frame at once (an empty box is
   not a loading state), loops while the canvas is on screen and stops when the
   function it returns is called. One canvas and 36 dots, like DotWave:
   animating DOM nodes would be a style write per dot per frame.
   requestAnimationFrame does not fire in a hidden tab, so a hidden tab pauses
   it too. */

const STILL = { from: "line" as ShapeName, to: "line" as ShapeName, progress: 0 };

export type DotFrame = { width: number; height: number; elapsed: number; reduced: boolean; color: string };

export type DotContext = Pick<
  CanvasRenderingContext2D,
  "clearRect" | "beginPath" | "arc" | "fill" | "fillStyle" | "globalAlpha"
>;

export function drawDots(context: DotContext, { width, height, elapsed, reduced, color }: DotFrame): void {
  const { from, to, progress } = reduced ? STILL : frameAt(elapsed);
  const a = SHAPE_POINTS[from];
  const b = SHAPE_POINTS[to];
  // Padding in proportion, so the drawing area keeps the 5:3 frame the
  // shapes were laid out for and the grid stays square.
  const padX = width * 0.08;
  const padY = height * 0.08;
  const t = elapsed / 1000;

  context.clearRect(0, 0, width, height);
  context.fillStyle = color;
  for (let i = 0; i < DOTS; i += 1) {
    const p = dotAt(a[i], b[i], progress, i);
    // A dot a shape does not use sits at weight 0, so it fades out and
    // shrinks on the way to its parking spot and back on the way out.
    const shown = Math.min(1, p.weight / 0.25);
    if (shown <= 0) continue;
    // A slow brightness wave across the frame keeps a held shape alive.
    const pulse = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(t * 2.2 - p.x * 7);
    context.globalAlpha = shown * Math.min(1, 0.3 + 0.55 * p.weight + 0.15 * pulse);
    context.beginPath();
    context.arc(
      padX + p.x * (width - 2 * padX),
      padY + p.y * (height - 2 * padY),
      (1.6 + 1.9 * p.weight + 0.35 * pulse) * (0.4 + 0.6 * shown),
      0,
      Math.PI * 2,
    );
    context.fill();
  }
  context.globalAlpha = 1;
}

export type DotOptions = {
  /* Draw as if the canvas were this many CSS pixels wide, then scale, so the
     dots grow with a bigger canvas instead of thinning out. Unset, the
     drawing uses the canvas's own size, as the build loader does. */
  logicalWidth?: number;
};

export function animateDots(node: HTMLCanvasElement, { logicalWidth }: DotOptions = {}): () => void {
  const context = node.getContext("2d");
  if (!context) return () => {};

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const color = getComputedStyle(document.documentElement).getPropertyValue("--pine").trim() || "#176b4e";
  let width = 0;
  let height = 0;
  let frame = 0;
  let origin = -1;
  let running = false;

  const resize = () => {
    const ratio = window.devicePixelRatio || 1;
    const rect = node.getBoundingClientRect();
    const cssWidth = Math.max(1, Math.floor(rect.width));
    const cssHeight = Math.max(1, Math.floor(rect.height));
    const scale = logicalWidth ? cssWidth / logicalWidth : 1;
    width = cssWidth / scale;
    height = cssHeight / scale;
    node.width = Math.floor(cssWidth * ratio);
    node.height = Math.floor(cssHeight * ratio);
    context.setTransform(ratio * scale, 0, 0, ratio * scale, 0, 0);
  };

  const draw = (time: number) => {
    if (origin < 0) origin = time;
    drawDots(context, { width, height, elapsed: time - origin, reduced, color });
  };

  const loop = (time: number) => {
    draw(time);
    frame = requestAnimationFrame(loop);
  };
  const play = () => {
    if (reduced || running) return;
    running = true;
    frame = requestAnimationFrame(loop);
  };
  const pause = () => {
    running = false;
    cancelAnimationFrame(frame);
  };

  resize();
  draw(performance.now());
  play();

  const sizes = new ResizeObserver(() => {
    resize();
    draw(performance.now());
  });
  sizes.observe(node);
  const seen = new IntersectionObserver(([entry]) => (entry?.isIntersecting ? play() : pause()));
  seen.observe(node);

  return () => {
    pause();
    sizes.disconnect();
    seen.disconnect();
  };
}
