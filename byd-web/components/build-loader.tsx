"use client";

import { useEffect, useRef, useState } from "react";
import { DOTS, SHAPE_POINTS, dotAt, frameAt, type ShapeName } from "@/lib/dot-shapes";

/* The plan, being found.

   Before a dashboard has a plan (the analyst, the data checks and the
   planner: 30 to 120 seconds on this machine) there is nothing to lay out
   yet, so the canvas shows one loader in its middle. It is drawn in the same
   pine dots as the block placeholders, walking through the shapes the model
   chooses between (a line, bars, a grid, a smooth line, an area), with the
   stage the backend reports underneath. There is no percentage because there
   is nothing to count until a plan exists.

   One canvas and 36 dots, like `DotWave`: animating DOM nodes would be a
   style write per dot per frame. It draws its first frame at once (an empty
   box is not a loading state) and pauses while it is off screen. */

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

const STILL = { from: "line" as ShapeName, to: "line" as ShapeName, progress: 0 };

export function BuildLoader({ label }: { label: string }) {
  const root = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [seconds, setSeconds] = useState(0);

  // A build started from the header while the canvas was scrolled down would
  // otherwise run out of sight.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    root.current?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }, []);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const context = node.getContext("2d");
    if (!context) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pine = getComputedStyle(document.documentElement).getPropertyValue("--pine").trim() || "#176b4e";
    let width = 0;
    let height = 0;
    let frame = 0;
    let origin = -1;
    let running = false;

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      const rect = node.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      node.width = Math.floor(width * ratio);
      node.height = Math.floor(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = (time: number) => {
      if (origin < 0) origin = time;
      const elapsed = time - origin;
      const { from, to, progress } = reduced ? STILL : frameAt(elapsed);
      const a = SHAPE_POINTS[from];
      const b = SHAPE_POINTS[to];
      // Padding in proportion, so the drawing area keeps the 5:3 frame the
      // shapes were laid out for and the grid stays square.
      const padX = width * 0.08;
      const padY = height * 0.08;
      const t = elapsed / 1000;

      context.clearRect(0, 0, width, height);
      context.fillStyle = pine;
      for (let i = 0; i < DOTS; i += 1) {
        const p = dotAt(a[i], b[i], progress, i);
        // A slow brightness wave across the frame keeps a held shape alive.
        const pulse = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(t * 2.2 - p.x * 7);
        context.globalAlpha = Math.min(1, 0.3 + 0.55 * p.weight + 0.15 * pulse);
        context.beginPath();
        context.arc(
          padX + p.x * (width - 2 * padX),
          padY + p.y * (height - 2 * padY),
          1.6 + 1.9 * p.weight + 0.35 * pulse,
          0,
          Math.PI * 2,
        );
        context.fill();
      }
      context.globalAlpha = 1;
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
  }, []);

  return (
    <div ref={root} className="flex w-full flex-col items-center gap-4 px-6 text-center">
      <div className="aspect-[5/3] w-full max-w-[320px] overflow-hidden rounded-[var(--r-card)] bg-sunken">
        <canvas ref={canvas} className="size-full" aria-hidden />
      </div>
      <div>
        <p role="status" className="text-[13.5px] font-semibold text-ink">
          <span key={label} className="stage-in">
            {label}
          </span>
        </p>
        <p className="mt-1 text-[12px] text-muted tabular">On this machine · {clock(seconds)}</p>
      </div>
    </div>
  );
}
