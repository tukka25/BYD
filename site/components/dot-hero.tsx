"use client";

import { useEffect, useRef } from "react";
import { animateDots } from "@/lib/dot-draw";

/* The build loader's animation (lib/dot-draw.ts, byte-identical to byd-web's),
   drawn larger and looping through every chart shape without end. It draws as
   if 320 px wide, the loader's size, then scales up, so the dots keep their
   proportions. It pauses off screen and in a hidden tab; with reduced motion it
   holds one still shape. */
export function DotHero() {
  const canvas = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    return animateDots(node, { logicalWidth: 320 });
  }, []);

  return (
    <div className="aspect-[5/3] w-full overflow-hidden rounded-[var(--r-panel)] bg-surface shadow-[var(--lift-1)]">
      <canvas ref={canvas} className="size-full" aria-hidden />
    </div>
  );
}
