"use client";

import { useEffect, useRef, useState } from "react";
import { themed, type PlotlyFigure } from "@/lib/plot-theme";

/* Renders a Plotly figure with the copy of Plotly bundled into this app.

   Not the CDN script the backend's dashboard_html used: the product's claim is
   that nothing leaves the machine, and a <script src="cdn.plot.ly"> breaks that
   on every chart. It also pinned the browser to one Plotly version, which was
   older than the one producing the figures.

   The model writes whatever Plotly it likes, so the figure is re-themed
   (lib/plot-theme.ts) before it is drawn. Otherwise every chart arrives in
   Plotly's default blue and the canvas looks like a different product from the
   rest of the page. */

/* When the data names no currency, the app does not guess one -- but you can
   say which it is, once, and have every unlabelled money column use it:
   NEXT_PUBLIC_DEFAULT_CURRENCY=AED (or USD, EUR, or a literal symbol).
   Unset means numbers get their separators and no symbol. Read here, not in
   lib/plot-theme.ts: Next inlines a NEXT_PUBLIC_ variable only where the code
   names it. */
const DEFAULT_CURRENCY = process.env.NEXT_PUBLIC_DEFAULT_CURRENCY ?? "";


export function Plot({
  figure,
  className,
  interactive = true,
  compact = false,
}: {
  figure: PlotlyFigure | null | undefined;
  className?: string;
  interactive?: boolean;
  compact?: boolean;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const node = host.current;
    if (!node || !figure) return;

    // Imported lazily so Plotly (a large bundle) stays out of the initial load
    // and never runs during SSR.
    import("plotly.js-dist-min")
      .then((mod) => {
        if (cancelled || !host.current) return;
        const Plotly = (mod.default ?? mod) as {
          react: (el: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
          Plots: { resize: (el: HTMLElement) => void };
          purge: (el: HTMLElement) => void;
        };
        const { data, layout } = themed(figure, DEFAULT_CURRENCY);
        const shown = compact
          ? {
              ...layout,
              margin: { l: 2, r: 2, t: 2, b: 2 },
              showlegend: false,
              xaxis: { ...((layout.xaxis as Record<string, unknown>) ?? {}), visible: false },
              yaxis: { ...((layout.yaxis as Record<string, unknown>) ?? {}), visible: false },
            }
          : layout;
        Plotly.react(host.current, data, shown, {
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
          staticPlot: !interactive,
        }).catch((error: unknown) => {
          if (!cancelled) setFailed(error instanceof Error ? error.message : "Could not draw this chart");
        });
      })
      .catch(() => {
        if (!cancelled) setFailed("Could not load the chart renderer");
      });

    const resize = () => {
      if (!host.current) return;
      import("plotly.js-dist-min").then((mod) => {
        const Plotly = (mod.default ?? mod) as { Plots: { resize: (el: HTMLElement) => void } };
        if (host.current) Plotly.Plots.resize(host.current);
      });
    };

    // Blocks are resized by dragging, so the plot follows its container rather
    // than only the window.
    const observer = new ResizeObserver(resize);
    observer.observe(node);

    /* Export is print-to-PDF, and Plotly writes explicit width/height onto the
       SVG from the last on-screen layout. The print stylesheet resizes the
       block but not the drawing inside it, so the figure has to be re-measured
       once print styles are in force -- and measured again afterwards, or the
       chart stays at page width on screen. */
    const printMedia = window.matchMedia("print");
    printMedia.addEventListener("change", resize);
    window.addEventListener("beforeprint", resize);
    window.addEventListener("afterprint", resize);

    return () => {
      cancelled = true;
      observer.disconnect();
      printMedia.removeEventListener("change", resize);
      window.removeEventListener("beforeprint", resize);
      window.removeEventListener("afterprint", resize);
      import("plotly.js-dist-min").then((mod) => {
        const Plotly = (mod.default ?? mod) as { purge: (el: HTMLElement) => void };
        if (node) Plotly.purge(node);
      });
    };
  }, [figure, interactive, compact]);

  if (failed) {
    return (
      <div className={`grid place-items-center p-4 text-center text-[13px] text-muted ${className ?? ""}`}>
        {failed}
      </div>
    );
  }

  return <div ref={host} className={`size-full ${className ?? ""}`} />;
}
