/* Built-in PDF export.

   Export used to be `window.print()`, so the file came out of the browser's
   print dialog — its margins, its headers, and a "Save as PDF" step in the
   middle of what should be one click. The app now builds the document itself.

   Two rules shape everything here:

   1. The page mirrors the canvas. Blocks land at their real x/y/w/h, because
      the arrangement is the user's work and an export that discards it is
      throwing that away.
   2. Charts are re-rendered by Plotly at the size they will occupy, never
      screenshotted. `Plotly.toImage` lays the axes out for the target size;
      a DOM capture would be a stretched bitmap and a second renderer to keep
      in step with plot.tsx.

   This module knows nothing about React. It takes the report and the blocks,
   finds each chart by `data-block-id`, and returns a file. */

import type { Block } from "@/lib/blocks";

/* --- page geometry -------------------------------------------------------
   A4 landscape: a 12-column dashboard is a wide thing. */
const PAGE_W = 297;
const PAGE_H = 210;
const MARGIN = 12;

const USABLE_W = PAGE_W - MARGIN * 2;
const USABLE_H = PAGE_H - MARGIN * 2;

const HEADER_FIRST = 24;
const HEADER_RUNNING = 11;
const FOOTER_H = 9;

/* Row height comes from the PAGE, not from the screen.

   The first instinct was to map the canvas 1:1 — a 1100px-wide canvas onto a
   273mm page, which makes a row 10.9mm and preserves every block's on-screen
   aspect ratio exactly. Measured against a real report, that is wrong: a
   default 9-row chart then eats 130mm of a 153mm page, so every block landed
   on a page of its own and a five-block report exported as five mostly-empty
   pages.

   A screen scrolls and a page does not, so the two cannot share a row height.
   The rule here instead: a default chart block (9 rows) takes 60% of a page's
   content height. Everything else follows from that. Blocks come out wider
   than they are tall, which is the right shape for a landscape page, and the
   charts are re-rendered by Plotly at that box rather than stretched into it,
   so nothing is distorted — only relaid out. */
const CONTENT_H_FIRST = USABLE_H - HEADER_FIRST - FOOTER_H;
const GAP_RATIO = 16 / 44; // the canvas's own gap-to-row proportion
const ROW_H = (CONTENT_H_FIRST * 0.6) / (9 + 8 * GAP_RATIO);
const GAP = ROW_H * GAP_RATIO;

const COL_W = (USABLE_W - GAP * 11) / 12;

const TITLE_H = 6; // the block's own title strip, inside its frame

const PINE: RGB = [23, 107, 78];
const INK: RGB = [23, 23, 28];
const BODY: RGB = [58, 58, 68];
const MUTED: RGB = [94, 94, 107];
const HAIRLINE: RGB = [216, 216, 224];
const WHITE: RGB = [255, 255, 255];

type RGB = [number, number, number];

/** Pixels per mm at 96dpi, for sizing a raster to its printed box. */
const PX_PER_MM = 96 / 25.4;

function blockW(w: number) {
  return w * COL_W + (w - 1) * GAP;
}

function blockH(h: number) {
  return h * ROW_H + (h - 1) * GAP;
}

function contentH(pageIndex: number) {
  return USABLE_H - (pageIndex === 0 ? HEADER_FIRST : HEADER_RUNNING) - FOOTER_H;
}

function contentTop(pageIndex: number) {
  return MARGIN + (pageIndex === 0 ? HEADER_FIRST : HEADER_RUNNING);
}

/* --- the mark ------------------------------------------------------------
   Drawn as vector primitives rather than embedded as an image: it is rounded
   rects, a polyline and circles, so it costs almost nothing and stays sharp
   at any zoom. Geometry mirrors components/logo.tsx on its 24-unit grid. */
const MARK_FIELD: [number, number][] = [
  [4.8, 20.2],
  [2.6, 20.8],
  [7.0, 19.8],
  [3.4, 21.0],
  [8.4, 20.4],
  [2.2, 20.9],
  [5.6, 19.6],
  [7.6, 20.7],
  [3.9, 20.1],
  [6.4, 20.9],
  [2.9, 20.3],
];

const MARK_LINE: [number, number][] = [
  [3.4, 18.6],
  [6.84, 14.4],
  [10.28, 17.2],
  [13.72, 11.8],
  [17.16, 14.6],
  [20.6, 8.2],
];

type Doc = {
  setFillColor: (r: number, g: number, b: number) => void;
  setDrawColor: (r: number, g: number, b: number) => void;
  setLineWidth: (w: number) => void;
  setLineCap: (s: string) => void;
  setLineJoin: (s: string) => void;
  setFont: (name: string, style?: string) => void;
  setFontSize: (n: number) => void;
  setTextColor: (r: number, g: number, b: number) => void;
  text: (t: string, x: number, y: number, o?: Record<string, unknown>) => void;
  getTextWidth: (t: string) => number;
  rect: (x: number, y: number, w: number, h: number, style?: string) => void;
  roundedRect: (
    x: number,
    y: number,
    w: number,
    h: number,
    rx: number,
    ry: number,
    style?: string,
  ) => void;
  circle: (x: number, y: number, r: number, style?: string) => void;
  line: (x1: number, y1: number, x2: number, y2: number) => void;
  addImage: (
    data: string,
    fmt: string,
    x: number,
    y: number,
    w: number,
    h: number,
    alias?: string,
    compression?: string,
  ) => void;
  addPage: () => void;
  setPage: (n: number) => void;
  splitTextToSize: (text: string, maxW: number) => string[];
  save: (name: string) => void;
  getNumberOfPages: () => number;
};

function drawMark(doc: Doc, x: number, y: number, size: number) {
  const s = size / 24;
  const px = (v: number) => x + v * s;
  const py = (v: number) => y + v * s;

  doc.setFillColor(...PINE);
  for (let i = 0; i < MARK_FIELD.length; i += 1) {
    const [top, bottom] = MARK_FIELD[i];
    const bx = px(0.95 + i * 2.1);
    const bw = 1.15 * s;
    doc.roundedRect(bx, py(top), bw, (bottom - top) * s, bw / 2, bw / 2, "F");
  }

  doc.setLineCap("round");
  doc.setLineJoin("round");

  // Keyline: the same polyline in the page colour, holding the line off the
  // field exactly as the on-screen mark does.
  doc.setDrawColor(...WHITE);
  doc.setLineWidth(4.1 * s);
  for (let i = 0; i < MARK_LINE.length - 1; i += 1) {
    const a = MARK_LINE[i];
    const b = MARK_LINE[i + 1];
    doc.line(px(a[0]), py(a[1]), px(b[0]), py(b[1]));
  }
  doc.setFillColor(...WHITE);
  for (const [cx, cy] of MARK_LINE) doc.circle(px(cx), py(cy), 3.1 * s, "F");

  doc.setDrawColor(...INK);
  doc.setLineWidth(1.8 * s);
  for (let i = 0; i < MARK_LINE.length - 1; i += 1) {
    const a = MARK_LINE[i];
    const b = MARK_LINE[i + 1];
    doc.line(px(a[0]), py(a[1]), px(b[0]), py(b[1]));
  }
  doc.setFillColor(...INK);
  for (const [cx, cy] of MARK_LINE) doc.circle(px(cx), py(cy), 2.25 * s, "F");

  doc.setLineCap("butt");
  doc.setLineJoin("miter");
}

/* --- notes ---------------------------------------------------------------
   text_body is sanitised HTML over a 14-tag allowlist. It is drawn as real
   text, not an image, so an exported note stays selectable and searchable.
   Inline strong/em survive: a paragraph is rendered as a sequence of styled
   runs with manual word wrapping, rather than flattened to one style. */

type Run = { text: string; bold: boolean; italic: boolean };
type TextBlock = { runs: Run[]; size: number; bold: boolean; indent: number; marker?: string };

function collectRuns(node: Node, bold: boolean, italic: boolean, out: Run[]) {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent ?? "";
    if (text) out.push({ text, bold, italic });
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  const tag = (node as Element).tagName.toLowerCase();
  const isBold = bold || tag === "strong" || tag === "b";
  const isItalic = italic || tag === "em" || tag === "i";
  node.childNodes.forEach((child) => collectRuns(child, isBold, isItalic, out));
}

function parseNote(html: string): TextBlock[] {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const out: TextBlock[] = [];

  const push = (el: Element, size: number, bold: boolean, indent: number, marker?: string) => {
    const runs: Run[] = [];
    collectRuns(el, bold, false, runs);
    const joined = runs.map((r) => r.text).join("").trim();
    if (joined) out.push({ runs, size, bold, indent, marker });
  };

  doc.body.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent ?? "").trim();
      if (text) out.push({ runs: [{ text, bold: false, italic: false }], size: 9, bold: false, indent: 0 });
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node as Element;
    switch (el.tagName.toLowerCase()) {
      case "h1":
      case "h2":
        push(el, 11.5, true, 0);
        break;
      case "h3":
        push(el, 10, true, 0);
        break;
      case "ul":
        el.querySelectorAll("li").forEach((li) => push(li, 9, false, 4, "•"));
        break;
      case "ol":
        el.querySelectorAll("li").forEach((li, i) => push(li, 9, false, 4, `${i + 1}.`));
        break;
      case "blockquote":
        push(el, 9, false, 4);
        break;
      default:
        push(el, 9, false, 0);
    }
  });

  return out;
}

/** Word-wrap styled runs inside a width, returning laid-out lines. */
function wrapRuns(doc: Doc, runs: Run[], maxW: number, size: number): Run[][] {
  doc.setFontSize(size);
  const lines: Run[][] = [];
  let line: Run[] = [];
  let width = 0;

  for (const run of runs) {
    doc.setFont("helvetica", run.bold ? (run.italic ? "bolditalic" : "bold") : run.italic ? "italic" : "normal");
    // Keep the spaces: splitting on them and re-joining loses runs of spacing
    // and makes "a **b** c" render as "a**b**c".
    const words = run.text.split(/(\s+)/).filter((w) => w !== "");
    for (const word of words) {
      const w = doc.getTextWidth(word);
      if (width + w > maxW && line.length > 0 && word.trim() !== "") {
        lines.push(line);
        line = [];
        width = 0;
      }
      if (line.length === 0 && word.trim() === "") continue; // no leading space
      line.push({ ...run, text: word });
      width += w;
    }
  }
  if (line.length > 0) lines.push(line);
  return lines;
}

function drawNote(doc: Doc, html: string, x: number, y: number, w: number, maxY: number): void {
  let cursor = y;
  for (const tb of parseNote(html)) {
    const lines = wrapRuns(doc, tb.runs, w - tb.indent, tb.size);
    const lineH = tb.size * 0.52;
    for (let i = 0; i < lines.length; i += 1) {
      if (cursor + lineH > maxY) return; // the frame is the limit; do not spill
      let cx = x + tb.indent;
      if (i === 0 && tb.marker) {
        doc.setFont("helvetica", "normal");
        doc.setFontSize(tb.size);
        doc.setTextColor(...MUTED);
        doc.text(tb.marker, x, cursor + lineH);
      }
      for (const run of lines[i]) {
        doc.setFont(
          "helvetica",
          run.bold ? (run.italic ? "bolditalic" : "bold") : run.italic ? "italic" : "normal",
        );
        doc.setFontSize(tb.size);
        doc.setTextColor(...(tb.bold ? INK : BODY));
        doc.text(run.text, cx, cursor + lineH);
        cx += doc.getTextWidth(run.text);
      }
      cursor += lineH + tb.size * 0.16;
    }
    cursor += tb.size * 0.3;
  }
}

/* --- charts --------------------------------------------------------------- */

type PlotlyFigureLike = { data: unknown; layout: unknown };

type PlotlyModule = {
  toImage: (
    gd: HTMLElement | PlotlyFigureLike,
    opts: { format: string; width: number; height: number; scale?: number },
  ) => Promise<string>;
};

/* plot.tsx sets the figure font to `var(--font-jakarta)` so charts match the
   page. Plotly's toImage renders into a detached tree where that custom
   property does not resolve, so every exported chart came out in the browser's
   serif default while the rest of the PDF was sans — the one thing in the
   document that did not look like the app.

   next/font puts the real family name in those same variables, so we read them
   off the document and substitute before rendering. */
function resolvedFonts(): { sans: string; display: string } {
  const fallback = "Helvetica, Arial, sans-serif";
  try {
    // next/font declares these variables on <body> (layout.tsx puts the font
    // classes there), not on :root — reading them off documentElement returns
    // empty and silently drops the export back to a generic face.
    const root = getComputedStyle(document.body ?? document.documentElement);
    const sans = root.getPropertyValue("--font-jakarta").trim();
    const display = root.getPropertyValue("--font-outfit").trim();
    return {
      sans: sans ? `${sans}, ${fallback}` : fallback,
      display: display ? `${display}, ${fallback}` : sans ? `${sans}, ${fallback}` : fallback,
    };
  } catch {
    return { sans: fallback, display: fallback };
  }
}

/** Deep-copy a figure, swapping any `var(--font-*)` reference for a real family. */
function withRealFonts<T>(value: T, fonts: { sans: string; display: string }): T {
  if (typeof value === "string") {
    return value
      .replace(/var\(--font-outfit\)/g, fonts.display)
      .replace(/var\(--font-jakarta\)/g, fonts.sans)
      .replace(/var\(--font-jetbrains-mono\)/g, "monospace") as unknown as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => withRealFonts(item, fonts)) as unknown as T;
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = withRealFonts(v, fonts);
    }
    return out as unknown as T;
  }
  return value;
}

async function chartImage(
  node: HTMLElement,
  wMm: number,
  hMm: number,
  fonts: { sans: string; display: string },
): Promise<string | null> {
  const opts = {
    format: "png",
    width: Math.max(80, Math.round(wMm * PX_PER_MM)),
    height: Math.max(60, Math.round(hMm * PX_PER_MM)),
    // 2x the printed box: crisp on paper without making the file enormous.
    scale: 2,
  };

  try {
    const mod = await import("plotly.js-dist-min");
    const Plotly = (mod.default ?? mod) as unknown as PlotlyModule;
    const gd = node as unknown as { data?: unknown; layout?: unknown };

    // Render from a copy of the figure rather than the live node, so the font
    // substitution never touches what is on screen.
    if (gd.data) {
      try {
        const figure = withRealFonts(
          { data: gd.data, layout: gd.layout ?? {} } as PlotlyFigureLike,
          fonts,
        );
        return await Plotly.toImage(figure, opts);
      } catch {
        // Fall through: a figure Plotly will not re-render from a plain object
        // is still better exported in the wrong font than not at all.
      }
    }

    return await Plotly.toImage(node, opts);
  } catch {
    return null;
  }
}

function chartNode(blockId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-block-id="${blockId}"] .js-plotly-plot`);
}

/* --- chrome ---------------------------------------------------------------- */

function drawFirstHeader(doc: Doc, title: string, sources: string[], date: string) {
  drawMark(doc, MARGIN, MARGIN - 1, 11);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(17);
  doc.setTextColor(...INK);
  doc.text(title, MARGIN + 14, MARGIN + 6.5);

  const meta = [sources.length > 0 ? sources.join(", ") : "Any source", date].join("  ·  ");
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  doc.setTextColor(...MUTED);
  doc.text(meta, MARGIN + 14, MARGIN + 12);

  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, MARGIN + 17, PAGE_W - MARGIN, MARGIN + 17);
}

function drawRunningHeader(doc: Doc, title: string) {
  drawMark(doc, MARGIN, MARGIN - 1, 7);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...MUTED);
  doc.text(title, MARGIN + 9.5, MARGIN + 4);
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, MARGIN + 7, PAGE_W - MARGIN, MARGIN + 7);
}

function drawFooter(doc: Doc, page: number, total: number) {
  const y = PAGE_H - MARGIN + 1;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text("Generated on this machine", MARGIN, y);
  const label = `${page} / ${total}`;
  doc.text(label, PAGE_W - MARGIN - doc.getTextWidth(label), y);
}

/* --- blocks ---------------------------------------------------------------- */

function drawFrame(doc: Doc, x: number, y: number, w: number, h: number, title: string) {
  // On screen, surfaces separate by value; on white paper a white card is
  // invisible, so the hairline is the print equivalent of that value step
  // rather than decoration.
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.3);
  doc.roundedRect(x, y, w, h, 2, 2, "S");

  if (title) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...INK);
    const lines = doc.splitTextToSize(title, w - 6);
    doc.text(lines[0], x + 3, y + 4.6);
  }
}

export type ExportReport = {
  title: string;
  sources: string[];
  blocks: Block[];
};

export type ExportResult = {
  filename: string;
  pages: number;
  blocks: number;
  chartsFailed: number;
};

function slug(value: string) {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "report"
  );
}

/**
 * Build the report as a PDF and hand it to the user as a download.
 * Resolves once the file has been produced.
 */
export async function exportReportToPdf(report: ExportReport): Promise<ExportResult> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({
    orientation: "landscape",
    unit: "mm",
    format: "a4",
    compress: true,
  }) as unknown as Doc;

  const date = new Date().toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  const ordered = [...report.blocks].sort((a, b) => (a.y - b.y) || (a.x - b.x));
  const fonts = resolvedFonts();

  let pageIndex = 0;
  let pageStartRow = ordered.length > 0 ? ordered[0].y : 0;
  let chartsFailed = 0;

  drawFirstHeader(doc, report.title, report.sources, date);

  for (const block of ordered) {
    const h = blockH(block.h);
    let top = contentTop(pageIndex) + (block.y - pageStartRow) * (ROW_H + GAP);

    // A block that would cross the page bottom starts the next page at its own
    // row, so blocks sharing rows stay side by side and none is ever sliced.
    if (top + h > contentTop(pageIndex) + contentH(pageIndex) && block.y > pageStartRow) {
      doc.addPage();
      pageIndex += 1;
      pageStartRow = block.y;
      drawRunningHeader(doc, report.title);
      top = contentTop(pageIndex);
    }

    const left = MARGIN + block.x * (COL_W + GAP);
    const w = blockW(block.w);
    // A block taller than a whole page cannot be placed by the rule above, so
    // it is clamped. Reachable: with ~10.9mm rows, 11 rows overflows page one.
    const drawH = Math.min(h, contentH(pageIndex));

    drawFrame(doc, left, top, w, drawH, block.title ?? "");

    const innerX = left + 3;
    const innerY = top + (block.title ? TITLE_H : 2);
    const innerW = w - 6;
    const innerH = drawH - (block.title ? TITLE_H : 2) - 2.5;

    if (block.kind === "text") {
      const html = block.text_body ?? "";
      if (html.trim()) drawNote(doc, html, innerX, innerY, innerW, top + drawH - 2);
      continue;
    }

    const node = chartNode(block.id);
    const image = node ? await chartImage(node, innerW, innerH, fonts) : null;

    if (image) {
      doc.addImage(image, "PNG", innerX, innerY, innerW, innerH, block.id, "FAST");
    } else {
      chartsFailed += 1;
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8.5);
      doc.setTextColor(...MUTED);
      doc.text("This chart could not be drawn.", innerX, innerY + innerH / 2);
    }
  }

  // Footers last: the total page count is only known once every block is placed.
  const total = doc.getNumberOfPages();
  for (let p = 1; p <= total; p += 1) {
    doc.setPage(p);
    drawFooter(doc, p, total);
  }

  // Local date, not toISOString(): at 00:30 in +04 the UTC date is still
  // yesterday, and the filename would disagree with the date in the header.
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const filename = `${slug(report.title)}-${stamp}.pdf`;
  doc.save(filename);

  return { filename, pages: total, blocks: ordered.length, chartsFailed };
}
