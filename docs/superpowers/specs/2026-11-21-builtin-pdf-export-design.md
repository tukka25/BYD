# Built-in PDF export

**Date:** 2026-11-21
**Status:** approved, implemented

## The problem

`Export` on the report canvas called `window.print()`. The file therefore came
out of Chrome's print dialog: the browser's own margins and headers, a
"Destination: Save as PDF" step, and whatever the OS print stack decided to do
with an absolutely-positioned grid. The app was asking the browser to produce
its deliverable and had no say in the result.

## What it does instead

The app builds the PDF itself and hands the user the file. One click, no
dialog, no browser chrome in the output.

## Decisions

**Layout mirrors the canvas.** Blocks land at their real `x/y/w/h`. The user
arranged the grid deliberately; an export that throws the arrangement away is
discarding their work. (Rejected: one-block-per-row stacking, which is what the
print path did; rejected: an export options sheet, since a dialog is the thing
being removed.)

**Charts render through Plotly, not the DOM.** Every block is a live Plotly
graph div, so `Plotly.toImage(node, { scale: 2 })` re-renders the figure at the
target size. Axis labels and ticks are laid out for that size rather than being
a bitmap stretched to fit. This is why the export does not use html2canvas: a
DOM screenshot is fuzzy, loses SVG text, and would be a second renderer to keep
in step with `plot.tsx`.

**jsPDF, lazy-imported.** MIT, pure JS, makes no network request at runtime, so
it does not touch the local-only guarantee — that rule is about runtime
requests, not about npm packages. It is imported inside the click handler, the
same pattern `plot.tsx` uses for Plotly, so it stays out of the initial bundle.

**A module that knows nothing about React.** `lib/export-pdf.ts` takes the
title, the sources and the blocks, and resolves each chart node by
`data-block-id`. `report-canvas.tsx` is already ~900 lines and should not grow
a PDF engine inside it.

## Geometry

A4 landscape (297×210mm), 12mm margins — landscape because a 12-column
dashboard is a wide thing.

**Row height comes from the page, not from the screen.** The first
implementation mapped the canvas 1:1 — a 1100px canvas onto a 273mm page,
giving `rowH = colW * 44/77 = 10.91mm` and preserving every block's on-screen
aspect ratio exactly. Measured against a real five-block report, that was
wrong: a default 9-row chart then eats 130mm of a 153mm page, so every block
landed on a page of its own and the export came out as **five** mostly-empty
pages. A screen scrolls and a page does not, so the two cannot share a row
height.

The shipped rule: a default chart block (9 rows) occupies 60% of a page's
content height.

```
contentH    = usableH - headerFirst - footer      = 153mm
gapRatio    = 16/44                               (the canvas's own proportion)
rowH        = contentH * 0.6 / (9 + 8*gapRatio)   = 7.72mm
gap         = rowH * gapRatio                     = 2.81mm
colW        = (usableW - 11*gap) / 12             = 20.17mm
blockW(w)   = w*colW + (w-1)*gap
blockH(h)   = h*rowH + (h-1)*gap
```

The same report is now three pages. Blocks come out wider than they are tall,
which is the right shape for a landscape page, and because Plotly relays each
figure out for its box rather than stretching it, nothing is distorted.

## Pagination

Blocks sorted by `(y, x)`. A page starts at some grid row; when the next block
would cross the page bottom, a new page starts at that block's row. Blocks
sharing rows stay side by side, and no block is ever sliced across a page.

A single block taller than one page cannot be placed by that rule, so its
height is clamped to the page. This is reachable: with 10.91mm rows, a block of
11 rows or more overflows the first page, and the canvas lets a user resize
that tall.

## Notes

`text_body` is sanitised HTML over a 14-tag allowlist, parsed with `DOMParser`
(the export only ever runs in the browser) into headings, paragraphs, lists and
blockquotes, and drawn as real PDF text — selectable and searchable, not an
image. Inline `strong`/`em` are kept by rendering each paragraph as a sequence
of styled runs with manual word wrapping, rather than flattening the paragraph
to one style.

## Chrome

First page: the mark, the report title, its sources, the date. Later pages: a
slim running header. Every page: `n / m`. The mark is drawn with vector
primitives (rounded rects, a polyline, circles) rather than embedded as an
image, because it is simple geometry and stays sharp at any zoom.

On paper each block gets a hairline border. On screen the design system
separates surfaces by value and bans decorative borders, but a white card on
white paper is invisible — the hairline is the print equivalent of that value
step, not decoration.

## The font trap

`plot.tsx` sets the figure font to `var(--font-jakarta)`. `toImage` renders
into a detached tree where that custom property does not resolve, so every
exported chart came out in the browser's serif default while the rest of the
PDF was sans — the one thing in the document that did not look like the app.
The export reads the real family names off those variables and substitutes
them into a copy of the figure.

They must be read from `document.body`, not `document.documentElement`:
`next/font` declares the variables on the body via `layout.tsx`, and reading
`:root` returns an empty string, which fails silently back to a generic face.

## Failure

A block whose chart cannot be rendered becomes a bordered box carrying its
title and a short line saying the chart could not be drawn. One bad block never
fails the export.

## Out of scope

No paper-size picker, no PNG or PowerPoint output, no server-side rendering.
The existing `@media print` CSS stays so ⌘P still produces something sane, but
it is no longer the Export path.
