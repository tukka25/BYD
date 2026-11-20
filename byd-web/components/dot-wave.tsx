"use client";

import { useEffect, useRef } from "react";

/* The wait, drawn.

   Generation takes 15 seconds a block, so the wait is a real state and gets a
   real treatment: a field of dots with a pulse travelling through it, the
   phase it is in, and how far along it is.

   Drawn on a canvas rather than as several hundred elements. Animating that
   many nodes through the DOM means a style write per dot per frame, which is
   exactly the kind of work that makes the rest of the page feel heavy — the
   mistake this canvas was built to avoid.

   Adapted from a dark reference to this product's light surface: the dots are
   the brand pine over the sunken grey rather than blue on black. */

const DOT_SPACING = 17;
const DOT_MIN = 0.9;
const DOT_MAX = 3.1;

export function DotWave({
  label,
  percent,
  className,
}: {
  label?: string;
  percent?: number | null;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const context = node.getContext("2d");
    if (!context) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let width = 0;
    let height = 0;

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
      const t = time / 1000;
      context.clearRect(0, 0, width, height);

      const columns = Math.floor(width / DOT_SPACING);
      const rows = Math.floor(height / DOT_SPACING);
      if (columns < 1 || rows < 1) return;

      // Centre the grid in whatever box it was given.
      const offsetX = (width - (columns - 1) * DOT_SPACING) / 2;
      const offsetY = (height - (rows - 1) * DOT_SPACING) / 2;

      // The pulse radiates from a point that drifts, so the field never
      // repeats on a beat you can count.
      const originX = width / 2 + Math.sin(t * 0.37) * width * 0.3;
      const originY = height / 2 + Math.cos(t * 0.29) * height * 0.3;
      const reach = Math.hypot(width, height) * 0.62;

      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) {
          const x = offsetX + column * DOT_SPACING;
          const y = offsetY + row * DOT_SPACING;

          const distance = Math.hypot(x - originX, y - originY) / reach;
          const envelope = Math.max(0, 1 - distance);
          const wave = 0.5 + 0.5 * Math.sin(distance * 9 - t * 2.6);
          const value = envelope * (0.3 + 0.7 * wave);

          const radius = DOT_MIN + value * (DOT_MAX - DOT_MIN);
          context.globalAlpha = 0.1 + value * 0.75;
          context.beginPath();
          context.arc(x, y, radius, 0, Math.PI * 2);
          context.fill();
        }
      }
      context.globalAlpha = 1;
    };

    const loop = (time: number) => {
      draw(time);
      frame = requestAnimationFrame(loop);
    };

    const start = () => {
      resize();
      context.fillStyle = "#176b4e";
      // Drawn once up front: a throttled tab may not run an animation frame
      // for a while, and an empty box is not a loading state.
      draw(0);
      if (reduced) return;
      frame = requestAnimationFrame(loop);
    };

    start();
    const observer = new ResizeObserver(() => {
      resize();
      if (reduced) draw(0);
    });
    observer.observe(node);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return (
    <div className={`relative size-full overflow-hidden rounded-[var(--r-card)] bg-sunken ${className ?? ""}`}>
      <canvas ref={canvas} className="size-full" aria-hidden />

      {label ? (
        <p
          aria-live="polite"
          className="absolute left-5 right-5 top-4 truncate text-[13.5px] font-semibold text-ink"
        >
          {label}
        </p>
      ) : null}

      {typeof percent === "number" ? (
        <span className="absolute bottom-4 right-5 rounded-[var(--r-pill)] bg-surface px-2.5 py-1 text-[12.5px] font-bold text-pine tabular">
          {Math.round(percent)}%
        </span>
      ) : null}
    </div>
  );
}
