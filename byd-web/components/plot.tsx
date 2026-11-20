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

/* --- money and magnitudes ------------------------------------------------
   A 9B model will not reliably remember d3 format strings, and a figure that
   prints 583271495.17 is harder to read than one that prints $583,271,495 --
   the difference is the whole point of a KPI. So the formatting is applied
   here, deterministically, to every figure from every model.

   The currency is taken from what the DATA says, never guessed: a field named
   `mrrUsd` or an axis titled "Revenue (EUR)" names its currency, and a field
   named `salePrice` does not. Where no currency is named, numbers still get
   their separators but no symbol is invented -- printing a dollar sign on a
   column that never said dollars is a wrong number, not a prettier one. */

const CURRENCIES: Array<[RegExp, string]> = [
  [/\busd\b|\$/i, "$"],
  [/\beur\b|€/i, "€"],
  [/\bgbp\b|£/i, "£"],
  [/\bjpy\b|¥/i, "¥"],
  [/\bcny\b|\brmb\b/i, "¥"],
  [/\binr\b|₹/i, "₹"],
  [/\baed\b|د\.إ/i, "AED "],
  [/\bsar\b/i, "SAR "],
  [/\bqar\b/i, "QAR "],
  [/\bkwd\b/i, "KWD "],
  [/\bbhd\b/i, "BHD "],
  [/\bomr\b/i, "OMR "],
  [/\bjod\b/i, "JOD "],
  [/\begp\b/i, "E£"],
  [/\bchf\b/i, "CHF "],
  [/\bcad\b/i, "CA$"],
  [/\baud\b/i, "A$"],
  [/\bbrl\b/i, "R$"],
  [/\bkrw\b|₩/i, "₩"],
  [/\btry\b|₺/i, "₺"],
  [/\bzar\b/i, "R"],
  [/\bmxn\b/i, "MX$"],
  [/\bngn\b|₦/i, "₦"],
];

function textOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "text" in value) {
    return String((value as { text?: unknown }).text ?? "");
  }
  return "";
}

/** Every label the figure carries, with camelCase split so `mrrUsd` reads. */
function figureWords(figure: PlotlyFigure): string {
  const layout = (figure.layout ?? {}) as Record<string, unknown>;
  const parts: string[] = [textOf(layout.title)];
  for (const axis of ["xaxis", "yaxis"]) {
    const value = layout[axis] as Record<string, unknown> | undefined;
    if (value) parts.push(textOf(value.title));
  }
  for (const raw of (figure.data ?? []) as Array<Record<string, unknown>>) {
    parts.push(String(raw.name ?? ""), textOf(raw.title));
    const number = raw.number as Record<string, unknown> | undefined;
    if (number) parts.push(String(number.prefix ?? ""), String(number.suffix ?? ""));
  }
  return parts.join(" ").replace(/([a-z0-9])([A-Z])/g, "$1 $2");
}

/* When the data names no currency, the app does not guess one -- but you can
   say which it is, once, and have every unlabelled money column use it:
   NEXT_PUBLIC_DEFAULT_CURRENCY=AED (or USD, EUR, or a literal symbol).
   Unset means numbers get their separators and no symbol. */
const DEFAULT_CURRENCY = symbolFor(process.env.NEXT_PUBLIC_DEFAULT_CURRENCY ?? "");

function symbolFor(value: string): string {
  const text = value.trim();
  if (!text) return "";
  for (const [pattern, symbol] of CURRENCIES) {
    if (pattern.test(text)) return symbol;
  }
  // Something we have no code for: use it as written.
  return text.length <= 3 ? text : `${text} `;
}

function detectCurrency(figure: PlotlyFigure): string {
  const words = figureWords(figure);
  for (const [pattern, symbol] of CURRENCIES) {
    if (pattern.test(words)) return symbol;
  }
  // Only money-ish measures take the default; a count of orders is not money.
  return MONEYISH.test(words) ? DEFAULT_CURRENCY : "";
}

/* A conservative read of d3's format mini-language: optional sign, symbol,
   zero-fill, width, group separator, precision, trim, and one type letter --
   and nothing after it. `#1f77b4` parses as far as `#1f` and then has `77b4`
   left over, which is how we tell a colour from a format. */
const D3_FORMAT = /^[-+( ]?[$#]?0?\d*,?(\.\d+)?~?[bcdefgnorsxX%]?$/;

/** A separator-ed format that keeps decimals only where they mean something. */
function numberFormat(value: unknown): string {
  const magnitude = Math.abs(Number(value));
  if (!Number.isFinite(magnitude)) return ",";
  if (magnitude >= 1000) return ",.0f";
  if (Number.isInteger(Number(value))) return ",";
  return ",.2f";
}

function allIndicators(figure: PlotlyFigure): boolean {
  const data = (figure.data ?? []) as Array<{ type?: string }>;
  return data.length > 0 && data.every((trace) => trace?.type === "indicator");
}

const MONEYISH =
  /\b(price|revenue|sales|cost|amount|value|spend|mrr|arr|gmv|gdp|profit|margin|income|salary|fee|budget|total|usd|eur|gbp|aed|sar|jpy|inr)\b/i;

/** The currency belongs on the axis that holds the money, not on both.

    Gated on the axis TITLE: a figure can plot money against a year, and a `$`
    on the year axis is worse than no `$` at all. An untitled axis is left
    alone for the same reason -- there is nothing to go on.

    No tick format is set: Plotly's own magnitudes ("100k") are already right,
    and forcing SI turns a year axis into "1.95k". */
function measureAxis(figure: PlotlyFigure, axis: "xaxis" | "yaxis", currency: string) {
  if (!currency) return {};
  const layout = (figure.layout ?? {}) as Record<string, unknown>;
  const title = textOf((layout[axis] as Record<string, unknown> | undefined)?.title).replace(
    /([a-z0-9])([A-Z])/g,
    "$1 $2",
  );
  return title && MONEYISH.test(title) ? { tickprefix: currency } : {};
}

function themed(figure: PlotlyFigure) {
  const kpi = allIndicators(figure);
  const currency = detectCurrency(figure);
  const horizontalBars = ((figure.data ?? []) as Array<{ type?: string; orientation?: string }>).some(
    (t) => t?.type === "bar" && t?.orientation === "h",
  );
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
    xaxis: {
      ...AXIS,
      ...(horizontalBars ? measureAxis(figure, "xaxis", currency) : {}),
      ...((figure.layout?.xaxis as object) ?? {}),
    },
    yaxis: {
      ...AXIS,
      ...(horizontalBars ? {} : measureAxis(figure, "yaxis", currency)),
      ...((figure.layout?.yaxis as object) ?? {}),
    },
  };

  const data = (figure.data ?? []).map((raw) => {
    const trace = { ...(raw as Record<string, unknown>) };
    const marker = { ...((trace.marker as Record<string, unknown>) ?? {}) };

    if (trace.type === "bar") {
      // Pill caps, as in the binding reference. A percentage gives a true
      // capsule at any bar width; a fixed radius only rounds the corners.
      marker.cornerradius = "50%";
      trace.marker = marker;

      // The value, above the bar. Reading a bar against a gridline is a
      // guess; the number is the answer. Left off when the model labelled
      // the bars itself, and above a dozen bars, where labels collide.
      const horizontal = trace.orientation === "h";
      const values = (horizontal ? trace.x : trace.y) as unknown[] | undefined;
      if (!trace.text && !trace.texttemplate && values && values.length <= 12) {
        // Five significant figures, trailing zeros trimmed: 437.68M rather
        // than 438M, and still 35.8k and 408 where that is the whole number.
        trace.texttemplate = `${currency}%{${horizontal ? "x" : "y"}:.5~s}`;
        trace.textposition = "outside";
        trace.cliponaxis = false;
        trace.textfont = { family: DISPLAY, size: 11.5, color: "#3a3a44" };
      }
    }
    if (trace.type === "indicator") {
      // The block header carries the label, so the figure does not repeat it.
      // No font size is set: Plotly then scales the number to the tile, which
      // is what a block you can drag-resize needs.
      trace.title = undefined;
      const number = { ...((trace.number as Record<string, unknown>) ?? {}) };
      number.font = { family: DISPLAY, color: "#121216" };
      /* A deliberate format the model chose is kept -- a percentage, a fixed
         number of decimals. Three are not:

         empty, so there is nothing to keep; an SI one, because a headline
         number exists to be read exactly and `.0s` turns 72,466 into "72k",
         which is the figure the KPI was supposed to tell you; and anything
         that is not a d3 format at all, which Plotly ignores in silence --
         a colour once arrived in this field and the number rendered raw. */
      const chosen = String(number.valueformat ?? "");
      if (!chosen || /s$/.test(chosen) || !D3_FORMAT.test(chosen)) {
        number.valueformat = numberFormat(trace.value);
      }
      if (currency && !number.prefix && !number.suffix) number.prefix = currency;
      trace.number = number;
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
