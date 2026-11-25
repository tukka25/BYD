/* The chart re-theme. Every Plotly figure from every model passes through
   `themed` before it is drawn, so a chart looks like the rest of the app
   instead of Plotly's defaults, and its numbers read as numbers: separators,
   a currency the data names, values above a dozen bars or fewer.

   Moved out of components/plot.tsx unchanged, so the landing page can carry a
   byte-identical copy (site/lib/plot-theme.ts, checked by
   site/tests/copies.test.mts). Its one outside input, the default currency,
   is a parameter: plot.tsx passes NEXT_PUBLIC_DEFAULT_CURRENCY, and the
   landing page passes the currency its dashboard file states. */

export type PlotlyFigure = {
  data?: unknown[];
  layout?: Record<string, unknown>;
};

// Mirrors --series-1..8 in globals.css. Pine, copper and slate lead so a chart
// looks like the rest of the app on sight; 4-8 extend without colliding in hue.
// There is no purple in this sequence, by design.
const SERIES = [
  "#176b4e",
  "#c2761b",
  "#3b5b8f",
  "#d23f2b",
  "#2f8f86",
  "#d9a93e",
  "#b8486f",
  "#6e7a8a",
];

/* Plotly Express bakes an explicit colour onto every trace from its own default
   qualitative sequence, and an explicit trace colour beats `layout.colorway`.
   So a figure the model generated arrives wearing Plotly's blue/red/green no
   matter what colorway we set -- which is why the charts kept their default
   palette while the rest of the app was re-themed.

   We swap those machine defaults for our series, by trace index, and leave any
   other colour alone. A colour the model actually chose is authoring, and
   re-theming is not re-authoring. */
const PLOTLY_DEFAULT_COLORS = new Set([
  // plotly, the default sequence for px
  "#636efa", "#ef553b", "#00cc96", "#ab63fa", "#ffa15a",
  "#19d3f3", "#ff6692", "#b6e880", "#ff97ff", "#fecb52",
  // D3 / tab10, the other sequence px reaches for
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]);

function rethemedColor(value: unknown, index: number): string | undefined {
  if (typeof value !== "string") return undefined;
  return PLOTLY_DEFAULT_COLORS.has(value.trim().toLowerCase())
    ? SERIES[index % SERIES.length]
    : undefined;
}

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

/* A currency mark the model wrote itself ("$", "£", "USD ") says what the
   model guessed, not what the data says: Edinburgh prices in pounds once came
   back as "$215.00", and a shop whose data names no currency as dollars. The
   data's currency (named in a title, an axis or a series, or the default
   currency) replaces it, and with none it goes. Any other prefix or suffix
   ("~", "+") is kept. */
const CURRENCY_MARK =
  /^\s*(?:[$€£¥₹₩₺₦]|E£|CA\$|A\$|R\$|MX\$|USD|EUR|GBP|JPY|CNY|RMB|INR|AED|SAR|QAR|KWD|BHD|OMR|JOD|EGP|CHF|CAD|AUD|BRL|KRW|TRY|ZAR|MXN|NGN)\s*$/i;

function isCurrencyMark(value: unknown): boolean {
  return typeof value === "string" && CURRENCY_MARK.test(value);
}

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
  }
  return parts.join(" ").replace(/([a-z0-9])([A-Z])/g, "$1 $2");
}

function symbolFor(value: string): string {
  const text = value.trim();
  if (!text) return "";
  for (const [pattern, symbol] of CURRENCIES) {
    if (pattern.test(text)) return symbol;
  }
  // Something we have no code for: use it as written.
  return text.length <= 3 ? text : `${text} `;
}

function detectCurrency(figure: PlotlyFigure, fallback: string): string {
  const words = figureWords(figure);
  for (const [pattern, symbol] of CURRENCIES) {
    if (pattern.test(words)) return symbol;
  }
  // Only money-ish measures take the default; a count of orders is not money.
  return MONEYISH.test(words) ? fallback : "";
}

/* A conservative read of d3's format mini-language: optional sign, symbol,
   zero-fill, width, group separator, precision, trim, and one type letter --
   and nothing after it. `#1f77b4` parses as far as `#1f` and then has `77b4`
   left over, which is how we tell a colour from a format. */
const D3_FORMAT = /^[-+( ]?[$#]?0?\d*,?(\.\d+)?~?[bcdefgnorsxX%]?$/;

/* The only endings that render a plain, readable number: fixed, integer,
   percent, or bare grouping. A format with a precision and NO type letter
   (`.0`) is the trap -- d3 falls back to general and prints `1e+6`. So are
   `s` and `e`, for the same reason: a headline number is there to be read. */
const READABLE_FORMAT = /[,df%]$/;

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
  /\b(price|revenue|sales|cost|spend|mrr|arr|gmv|gdp|profit|margin|income|salary|fee|budget|usd|eur|gbp|aed|sar|jpy|inr)\b/i;

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

/** The figure, re-themed. `defaultCurrency` is the currency for money columns
    that name none: a code (AED, USD, GBP) or a literal symbol. Empty means
    no symbol is invented. */
export function themed(figure: PlotlyFigure, defaultCurrency = "") {
  const kpi = allIndicators(figure);
  const currency = detectCurrency(figure, symbolFor(defaultCurrency));
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

  // An axis currency the model wrote gives way to the data's (see CURRENCY_MARK).
  for (const axis of ["xaxis", "yaxis"] as const) {
    const value = layout[axis] as Record<string, unknown>;
    if (isCurrencyMark(value.tickprefix)) value.tickprefix = currency || undefined;
  }
  const data = (figure.data ?? []).map((raw, index) => {
    const trace = { ...(raw as Record<string, unknown>) };
    const marker = { ...((trace.marker as Record<string, unknown>) ?? {}) };

    const markerColor = rethemedColor(marker.color, index);
    if (markerColor) {
      marker.color = markerColor;
      trace.marker = marker;
    }

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

         empty, so there is nothing to keep; anything that does not end in a
         readable type, because a headline number is there to be read and
         `.0s`, `.0e` and bare `.0` print "72k", "1e+6" and "1e+6"; and
         anything that is not a d3 format at all, which Plotly ignores in
         silence -- a colour once arrived in this field and rendered raw. */
      // The model's own currency marks give way to the data's (see CURRENCY_MARK).
      const hadMark = isCurrencyMark(number.prefix) || isCurrencyMark(number.suffix);
      if (isCurrencyMark(number.prefix)) delete number.prefix;
      if (isCurrencyMark(number.suffix)) delete number.suffix;
      // d3's "$" flag prints a dollar sign: a currency mark like the others.
      const chosen = String(number.valueformat ?? "").replace("$", "");
      number.valueformat =
        chosen && D3_FORMAT.test(chosen) && READABLE_FORMAT.test(chosen) ? chosen : numberFormat(trace.value);
      if (currency && !number.prefix && (hadMark || !number.suffix)) number.prefix = currency;
      trace.number = number;
      trace.delta = {
        ...((trace.delta as Record<string, unknown>) ?? {}),
        increasing: { color: "#176b4e" },
        decreasing: { color: "#d23f2b" },
        font: { family: DISPLAY },
      };
      if (trace.gauge) {
        const gauge = { ...(trace.gauge as Record<string, unknown>) };
        gauge.bar = { ...((gauge.bar as Record<string, unknown>) ?? {}), color: "#176b4e" };
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
      const lineColor = rethemedColor(line.color, index);
      if (lineColor) line.color = lineColor;
      trace.line = line;
    }
    return trace;
  });

  return { data, layout };
}
