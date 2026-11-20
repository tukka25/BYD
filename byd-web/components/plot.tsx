"use client";

import { useEffect, useRef, useState } from "react";

/* Renders a Plotly figure with the copy of Plotly bundled into this app.

   Not the CDN script the backend's dashboard_html used: the product's claim is
   that nothing leaves the machine, and a <script src="cdn.plot.ly"> breaks that
   on every chart. It also pinned the browser to one Plotly version, which was
   older than the one producing the figures.

   The model writes whatever Plotly it likes, so the figure is re-themed here
   before it is drawn. Otherwise every chart arrives in Plotly's default blue
   and the canvas looks like a different product from the rest of the page. */

type PlotlyFigure = {
  data?: unknown[];
  layout?: Record<string, unknown>;
};

const SERIES = [
  "#5b3df5",
  "#f5a524",
  "#f2563f",
  "#0e9e8e",
  "#9b5cf6",
  "#2b7fff",
  "#d9479b",
  "#7a8699",
];

const AXIS = {
  gridcolor: "#e7e7ec",
  zerolinecolor: "#d8d8e0",
  linecolor: "#d8d8e0",
  tickfont: { color: "#5e5e6b", size: 11 },
  title: { font: { color: "#5e5e6b", size: 12 } },
  automargin: true,
};

const DISPLAY = "var(--font-outfit), system-ui, sans-serif";

function allIndicators(figure: PlotlyFigure): boolean {
  const data = (figure.data ?? []) as Array<{ type?: string }>;
  return data.length > 0 && data.every((trace) => trace?.type === "indicator");
}

function themed(figure: PlotlyFigure) {
  const kpi = allIndicators(figure);
  const layout: Record<string, unknown> = {
    ...(figure.layout ?? {}),
    colorway: SERIES,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "var(--font-jakarta), system-ui, sans-serif", color: "#3a3a44", size: 12 },
    // A KPI has no axes to label, so it gets the whole tile.
    margin: kpi ? { l: 12, r: 12, t: 8, b: 8 } : { l: 52, r: 18, t: 12, b: 42 },
    // The block header already names the chart, so a second title inside the
    // plot repeats it and steals vertical space.
    title: undefined,
    showlegend: kpi ? false : ((figure.layout as Record<string, unknown>)?.showlegend ?? true),
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      x: 0,
      font: { size: 11, color: "#5e5e6b" },
      bgcolor: "rgba(0,0,0,0)",
    },
    hoverlabel: {
      bgcolor: "#ffffff",
      bordercolor: "#d8d8e0",
      font: { color: "#121216", size: 12, family: "var(--font-jakarta), sans-serif" },
    },
    xaxis: { ...AXIS, ...((figure.layout?.xaxis as object) ?? {}) },
    yaxis: { ...AXIS, ...((figure.layout?.yaxis as object) ?? {}) },
  };

  const data = (figure.data ?? []).map((raw) => {
    const trace = { ...(raw as Record<string, unknown>) };
    const marker = { ...((trace.marker as Record<string, unknown>) ?? {}) };

    if (trace.type === "bar") {
      // Pill caps, as in the binding reference. A percentage gives a true
      // capsule at any bar width; a fixed radius only rounds the corners.
      marker.cornerradius = "50%";
      trace.marker = marker;
    }
    if (trace.type === "indicator") {
      // The block header carries the label, so the figure does not repeat it.
      // No font size is set: Plotly then scales the number to the tile, which
      // is what a block you can drag-resize needs.
      trace.title = undefined;
      trace.number = {
        ...((trace.number as Record<string, unknown>) ?? {}),
        font: { family: DISPLAY, color: "#121216" },
      };
      trace.delta = {
        ...((trace.delta as Record<string, unknown>) ?? {}),
        increasing: { color: "#0e9e8e" },
        decreasing: { color: "#f2563f" },
        font: { family: DISPLAY },
      };
      if (trace.gauge) {
        const gauge = { ...(trace.gauge as Record<string, unknown>) };
        gauge.bar = { ...((gauge.bar as Record<string, unknown>) ?? {}), color: "#5b3df5" };
        gauge.bgcolor = "#e7e7ec";
        gauge.bordercolor = "rgba(0,0,0,0)";
        trace.gauge = gauge;
      }
      return trace;
    }
    if (trace.type === "scatter" || trace.type === "scattergl") {
      const line = { ...((trace.line as Record<string, unknown>) ?? {}) };
      // Thick lines, per the reference. The round caps cannot be set here --
      // Plotly exposes no scatter line-cap option -- so globals.css sets them.
      line.width = line.width ?? 3.25;
      line.shape = line.shape ?? "spline";
      line.smoothing = 0.6;
      trace.line = line;
    }
    return trace;
  });

  return { data, layout };
}

export function Plot({
  figure,
  className,
}: {
  figure: PlotlyFigure | null | undefined;
  className?: string;
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
        const { data, layout } = themed(figure);
        Plotly.react(host.current, data, layout, {
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
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
  }, [figure]);

  if (failed) {
    return (
      <div className={`grid place-items-center p-4 text-center text-[13px] text-muted ${className ?? ""}`}>
        {failed}
      </div>
    );
  }

  return <div ref={host} className={`size-full ${className ?? ""}`} />;
}
