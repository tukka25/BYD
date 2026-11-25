"use client";

import { useEffect, useRef, useState } from "react";
import { DASHBOARD_DATA } from "@/components/dashboard-data";
import { loadPlotly, type PlotlyApi } from "@/components/plotly";
import { themed } from "@/lib/plot-theme";

type View = { phase: "waiting" } | { phase: "drawn" } | { phase: "failed"; message: string };

/* One chart of a dashboard, drawn with the app's re-theme, with hover on and
   zoom and the mode bar off. Until it is drawn, its card shows an empty frame
   of the right size, never an image standing in for the chart. */
export function LazyChart({
  dashboard,
  index,
  currency,
  indicator,
}: {
  dashboard: string;
  index: number;
  currency: string;
  indicator: boolean;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState<View>({ phase: "waiting" });

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let cancelled = false;
    let sizes: ResizeObserver | null = null;
    let drawnWith: PlotlyApi | null = null;

    const draw = async () => {
      const loaded = await Promise.all([loadPlotly(), DASHBOARD_DATA[dashboard]()]).catch(() => null);
      if (cancelled) return;
      if (!loaded) {
        setView({ phase: "failed", message: "Charts could not load" });
        return;
      }
      const [Plotly, data] = loaded;
      const figure = data.blocks[index]?.figure;
      if (!figure) {
        setView({ phase: "failed", message: "This chart could not be drawn" });
        return;
      }
      const { data: traces, layout } = themed(figure, currency);
      const still = {
        ...layout,
        dragmode: false,
        xaxis: { ...((layout.xaxis as Record<string, unknown>) ?? {}), fixedrange: true },
        yaxis: { ...((layout.yaxis as Record<string, unknown>) ?? {}), fixedrange: true },
      };
      const drawn = await Plotly.react(node, traces, still, {
        displayModeBar: false,
        responsive: true,
        scrollZoom: false,
        doubleClick: false,
      }).then(
        () => true,
        () => false,
      );
      if (cancelled) {
        if (drawn) Plotly.purge(node);
        return;
      }
      if (!drawn) {
        setView({ phase: "failed", message: "This chart could not be drawn" });
        return;
      }
      drawnWith = Plotly;
      setView({ phase: "drawn" });
      sizes = new ResizeObserver(() => Plotly.Plots.resize(node));
      sizes.observe(node);
    };

    const seen = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        seen.disconnect();
        void draw();
      },
      { rootMargin: "600px 0px" },
    );
    seen.observe(node);

    return () => {
      cancelled = true;
      seen.disconnect();
      sizes?.disconnect();
      // Purge only a chart this instance drew. Loading Plotly just to clean up
      // would load it at page load, under React's development double mount.
      drawnWith?.purge(node);
    };
  }, [dashboard, index, currency]);

  // data-chart (waiting, drawn or failed) changes nothing on screen:
  // scripts/previews.mjs reads it to take its pictures only once every chart
  // is drawn and unveiled, and to stop on a chart that failed.
  return (
    <div data-chart={view.phase} className="relative size-full">
      <div ref={host} className={`size-full ${indicator ? "[&_.cartesianlayer]:hidden" : ""}`} />
      {view.phase === "waiting" ? (
        <div className="absolute inset-0 rounded-[var(--r-card)] bg-sunken/50" aria-hidden />
      ) : null}
      {view.phase === "failed" ? (
        <p className="absolute inset-0 grid place-items-center p-4 text-center text-[14px] text-body">
          {view.message}
        </p>
      ) : null}
    </div>
  );
}
