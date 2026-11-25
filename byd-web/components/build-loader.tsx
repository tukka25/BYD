"use client";

import { useEffect, useRef, useState } from "react";
import { animateDots } from "@/lib/dot-draw";

/* The plan, being found.

   Before a dashboard has a plan (the analyst, the data checks and the
   planner: 30 to 120 seconds on this machine) there is nothing to lay out
   yet, so the canvas shows one loader in its middle. It is drawn in the same
   pine dots as the block placeholders, walking through every kind of chart
   the model can draw (lib/dot-shapes.ts), with the stage the backend reports
   underneath. There is no percentage because there is nothing to count until
   a plan exists.

   The canvas is drawn by lib/dot-draw.ts, which the landing page's hero
   shares: one canvas and 36 dots, the first frame drawn at once, paused
   while it is off screen. */

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

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
    return animateDots(node);
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
