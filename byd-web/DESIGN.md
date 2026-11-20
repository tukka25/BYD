# PromptDash — design system

Derived from the shipped build, not from intentions. Every value below is one
you can find in the code; where a number was measured (contrast, size) the
measurement is given rather than an adjective.

Surface mode: **Operate**. The visitor is here to finish a task — ask a
question, read the answer, arrange a report. Brand lives in precision, not in
expression. Scanability and native expectations outrank personality.

Binding reference for layout: `design/references/02-violet-amber-console.webp`
— its **structure** only. Its violet/amber palette is superseded and is now an
anti-reference for colour.
`01-gilded-admin.webp` is kept for its information architecture only and is an
**anti-reference** for surface treatment.

---

## 1. The one idea

**Value separates, not lines.** A near-white card on a light grey canvas, with
a shadow only where something genuinely floats. The previous build was
neumorphic — `#e0e5ec` with a paired inset *and* outset shadow on every
surface — which made everything look equally important and nothing look
clickable. Nothing in this system carries a border for decoration.

---

## 2. Colour

All tokens live in `app/globals.css` under `:root` and are re-exported to
Tailwind through `@theme inline`. Use the Tailwind names (`bg-surface`,
`text-muted`); never a raw hex in a component.

### Surfaces

| Token | Value | Use |
|---|---|---|
| `--canvas` | `#efeff2` | The page. Nothing else is this colour. |
| `--surface` | `#ffffff` | Cards, panels, popovers, the sidebar. |
| `--surface-sunken` | `#e7e7ec` | Wells: segmented tracks, textareas, chips, hover. |
| `--surface-inverse` | `#17171c` | Code blocks only. |

### Text — every value measured on `--canvas`

| Token | Value | Contrast | Use |
|---|---|---|---|
| `--ink` | `#121216` | 16.3:1 | Headings, block titles, values, active nav. |
| `--body` | `#3a3a44` | 9.8:1 | Paragraphs, note bodies, default button text. |
| `--muted` | `#5e5e6b` | **5.56:1** | The smallest text in the app. Still clears AA body. |
| `--on-dark` | `#f4f4f7` | — | Text on `--surface-inverse`. |

`--muted` is the floor. There is no lighter text colour, and labels are never
set in `--hairline` — the reference image does that and it measures 1.3:1.

### Lines

`--hairline #d8d8e0` and `--hairline-strong #c3c3cf`. Borders and scrollbar
thumbs only; **never text, never an icon that carries meaning**.

### Brand

| Token | Value | Rules |
|---|---|---|
| `--pine` | `#176b4e` | The one accent. 5.6:1 as text on canvas; takes white text at 6.5:1. Primary buttons, active state, focus ring, caret, selection, series 1. |
| `--pine-wash` | `#e4f0ea` | Active nav, chips, the avatar disc. Pine on it measures 5.5:1. |
| `--copper` | `#c2761b` | Fills and caution. Carries `--ink` at 5.3:1, never white. |
| `--coral` | `#d23f2b` | Fills and destructive. Takes white at 4.7:1, so danger needs no size rule. |
| `--slate` | `#3b5b8f` | Neutral categories — a source kind, a count. 5.9:1 as text; white at 6.8:1. |

Pine is deliberately the same green that marks "running on this machine": the
brand colour **is** the product's claim, so the thing that earns the accent is
"this ran here". The old `--teal` is gone, absorbed into pine.

**There is no purple in this system**, the chart series included. The previous
build led on `--violet #5b3df5` with a second purple hiding at series 5
(`#9b5cf6`); both are gone and neither comes back.

Each has a `-wash` tint for chip and alert backgrounds. Alert text uses the
darkened pairs, now tokens rather than hex literals in components:
`--coral-ink #a8331f` (5.6:1 on its wash), `--copper-ink #8a5214` (5.6:1) and
`--slate-ink #2e4871` (7.8:1), so a badge still reads at 12px.

### Chart series

```
1 #176b4e   2 #c2761b   3 #3b5b8f   4 #d23f2b
5 #2f8f86   6 #d9a93e   7 #b8486f   8 #6e7a8a
```

Pine, copper and slate lead so a chart looks like the rest of the app on
sight; 4–8 extend without colliding in hue, and none of them is purple. The
order is applied as Plotly's `colorway` in `components/plot.tsx`.

> **`colorway` alone does not re-theme a figure, and this doc used to claim it
> did.** Plotly Express bakes an explicit colour onto every trace from its own
> default sequence, and an explicit trace colour beats `layout.colorway`. So
> every generated chart kept Plotly's `#636efa` blue while the rest of the app
> was re-themed. `plot.tsx` now swaps a trace colour **only** when it matches a
> known Plotly default (the `plotly` and `D3` sequences), replacing it with our
> series by trace index. Any other colour is left alone: a colour the model
> actually chose is authoring, and re-theming is not re-authoring.

---

## 3. Type

Three faces, loaded with `next/font` at build time and served from this
origin. **No webfont request leaves the machine** — that is a product
constraint, not a performance preference.

| Role | Face | Where |
|---|---|---|
| Display | **Outfit** 500–800 | `h1`–`h4`, block titles, KPI numerals |
| UI | **Plus Jakarta Sans** 400–700 | Everything else; holds its shape at 13px |
| Mono | **JetBrains Mono** 400–500 | Generated code, file names, the model id |

Headings carry `letter-spacing: -0.028em` and `text-wrap: balance`.

### The scale as shipped

| px | Use |
|---|---|
| 34 / 26 | Page title (desktop / below `sm`) |
| 32 | Login headline |
| 19 / 21 | Wordmark |
| 18 | Empty-state heading |
| 15 | Block title, large button |
| 14 | Body, default button, inputs |
| 13.5 | Nav item |
| 13 | Field label, small button, segmented item |
| 12 | Hints, chips, captions |
| 11.5 | Sidebar meta, code |
| 11 | Group label (uppercase, `0.1em`), axis ticks, source name |

Figures use `font-variant-numeric: tabular-nums` (`.tabular`, and every table
cell) so columns line up and a value does not jitter as it updates.

---

## 4. Form

**Radii** — `--r-panel 24px` (panels, blocks), `--r-card 18px` (inner cards,
alerts, wells), `--r-control 12px` (buttons, inputs, nav items),
`--r-pill 999px` (chips, segmented, avatars). Smaller one-offs: 10–11px on the
logo tile, 8px on inline edit fields, 6px on checkboxes and bar caps.

**Elevation** — offset *and* blur, never a zero-offset halo.

```
--lift-1     0 1px 2px / 0.04, 0 2px 8px / 0.04      resting cards
--lift-2     0 2px 4px / 0.06, 0 12px 28px / 0.10    the ask bar, the drawer
--lift-drag  0 8px 16px / 0.10, 0 24px 56px pine/0.20     a block being dragged
```

A block picks up `--lift-drag` while it is dragged or resized, so the thing in
your hand is unambiguous.

---

## 5. Components (`components/ui.tsx`)

Every control in the app is built from these. A stock `<button>` or `<input>`
never appears inside a committed surface.

- **Panel** — `rounded-[24px] bg-surface shadow-[--lift-1]`. No border.
- **Button** — variants `primary` (pine/white), `secondary` (white with a
  hairline inset ring), `ghost`, `danger`. Sizes `sm` 32px / `md` 40px /
  `lg` 48px. `active:translate-y-px`; disabled drops to 45% and loses pointer
  events.
- **IconButton** — a 36px circle, `--muted` at rest, tinting to `--ink` (or
  coral for `tone="danger"`) on hover. Always carries `aria-label` and
  `title`; this is the only control that ships without a visible label.
- **Chip** — pill, 12px semibold, five tones, each a wash with its darkened
  text pair. Each tone has a job: `pine` is live or succeeded, `slate` labels a
  neutral category, `copper` cautions, `coral` failed, `neutral` is inert. Pine
  is the only green, so a "Database" chip and an "Active" chip sitting side by
  side stay readable as two different kinds of statement.
- **Segmented** — `role="tablist"`, a sunken track with a white lifted pill on
  the active option. Used for Edit / View.
- **Field** + `inputClass` — 44px tall, hairline inset ring, focus swaps to a
  2px pine ring. Label 13px semibold ink above, hint 12px muted below.
- **EmptyState** — washed icon tile, 18px heading, muted body capped at
  `max-w-sm`, one action.

**Icons** are lucide-react at **`strokeWidth={2.25}`**, everywhere. One
exception, deliberate: the 13px tick inside a filled checkbox (3 — it
disappears at 2.25). A third weight is a bug, not a judgement call. The logo is
not in this system at all — it is drawn geometry, not a stroked icon, and it
never takes a lucide weight.

---

## 5a. The mark

`components/logo.tsx`. A dense field of thin bars is the raw data in your file;
the bold node-and-line polyline crossing it is what the model found in that
data, held off the field by a keyline so it stays readable wherever it sits.
That is the product in one drawing: your data, and the answer drawn through it
on this machine.

What it replaced: lucide's `ChartNoAxesColumn` in a tinted rounded square. A
stock icon in a coloured squircle is the default every tool arrives at, and the
tile was doing the work the mark should do. **The mark now sits bare next to
the wordmark — no tile behind it**, except on the favicon, where a tab needs
the tile to separate the mark from the browser chrome.

**Two cuts, not one scaled drawing.**

| Cut | Contents | Where |
|---|---|---|
| `LogoMark` | 11 bars, 6 nodes | 28px and above: sidebar, login, mobile bar |
| `LogoMarkCompact` | 4 bars, 3 nodes, heavier line | the favicon and anything under 28px |

Eleven hairlines at 16px average out to grey mush, so the small size gets its
own drawing. A logo that is only legible at one size is a logo with one size.

The keyline colour is a prop, not a constant, because it has to match whatever
sits behind the mark: `--surface` in the sidebar, `--canvas` on the mobile bar,
pine on the favicon tile.

`app/icon.svg` is the browser tab; `app/apple-icon.png` is the touch icon, and
it is full-bleed and square on purpose — iOS applies its own corner mask, and
Apple touch icons cannot be SVG.

> **Hard rule.** The mark's resting state is the finished drawing. The
> animation is opt-in per surface and is never what makes the mark appear: a
> logo that is blank for the first second of every page load is a broken logo,
> not an animated one. It plays on `/login`, where the lockup is the first
> thing on the page, and nowhere else.

The order of the animation is the product: the bars rise (your data, already on
this machine), the line draws itself through them (the model reading it), then
the nodes land (the answer). The keyline draws in step with the line it
protects — drawn all at once it cuts a canvas-coloured swath through the field
before the ink line arrives to fill it, which reads as a rendering fault.
Transform and `stroke-dashoffset` only; neither forces paint.
`prefers-reduced-motion: reduce` drops the whole thing to the finished state.

---

## 6. Layout

**Shell** (`components/app-shell.tsx`) — a 248px sidebar holding Reports and
Data, the local-model card, and the account row. Below `lg` it becomes a
drawer behind a scrim with its own top bar; a fixed rail leaves a 375px screen
a sliver of the report.

The shell itself never scrolls: it is `h-dvh overflow-hidden`, and each route
scrolls inside its own `.app-scroll` region. That is what lets the canvas keep
a static ask bar at its foot instead of one floating over the blocks.

**Canvas** (`components/report-canvas.tsx`) — `react-grid-layout`, 12 columns,
`rowHeight: 44`, `margin: [16, 16]`, vertical compaction, dragged by the block
header (`.block-drag`).

| Container width | ≥900 | ≥700 | ≥540 | ≥400 | 0 |
|---|---|---|---|---|---|
| Columns | 12 | 12 | 6 | 4 | 2 |

> These are **container** widths, not viewport widths. `WidthProvider`
> measures the element it wraps, and the canvas sits inside a 248px sidebar
> plus its own padding — so a 1280px laptop has a ~992px canvas. Reading these
> as viewport widths is how that laptop silently lands on a 6-column grid.

Default block sizes, in grid units: **chart 6×9**, **metric 4×4**,
**text 12×3**.

> **Hard rule.** One layout is stored per block, in 12 columns. At a narrower
> breakpoint the grid clamps every block to fit, so writing that layout back
> would permanently squash a report arranged on a wide screen. Arranging is
> offered **only** where the grid still has all 12 columns; below that,
> dragging and resizing are off and the canvas says so in a line rather than
> accepting gestures it will discard.

The source chip under the report title is a control, not a label: it opens the
picker for what this report may read, and that choice is enforced — a report
that names its sources is answered only from those.

The ask bar is the last child of the canvas column, capped at `max-w-3xl`. It
is not a floating action button and not a fixed overlay: it is how every block
on the canvas gets made, so it stays in one place, always visible, with the
grid scrolling above it.

---

## 7. Motion

One authored moment: a block arrives on the canvas and settles into place —
`block-settle`, 520ms on `--ease-out` (`cubic-bezier(.16,1,.3,1)`), from
`translateY(10px) scale(.985)`. Everything else is a state change: 150ms on
colour, 200ms on the segmented pill, 300ms on the drawer.

**Opacity and transform only.** The settle originally animated a `filter:
blur()` too. It looked good and cost real frames: a filter takes the block —
chart SVG and all — off the compositor and makes it rasterise, which is felt
most while dragging one. Nothing on the canvas animates a property that
forces paint.

Generation takes 13–15s a block, so the wait is a real state and gets a real
treatment. `components/dot-wave.tsx` draws a field of pine dots with a pulse
travelling through it, on a canvas rather than as several hundred elements —
animating that many nodes through the DOM is a style write per dot per frame.
A first frame is drawn synchronously, because a throttled tab may not run an
animation frame for a while and an empty box is not a loading state.
(`.generating`, a pine sweep across a sunken bar, remains for skeletons.)

**One click lays the whole thing out.** Generating a dashboard puts a
placeholder down for every planned block, in its final position and size, and
each one loads in place with the dot field and the question it is answering.
The dashboard assembles in front of you rather than growing a tile at a time,
and nothing moves when a block arrives because its placeholder was already the
right shape. Placeholders are pinned (`static`) and are filtered out of any
layout save — they are not blocks.

**What the loader says is true.** Building a whole dashboard streams, so it
shows a real count — blocks finished out of blocks planned — as a percentage.
A single block is one request that answers at the end, so there is no real
number and none is shown: it names the stage instead, on the schedule those
stages were measured at. A progress bar that is really a timer is a lie told
with a number.

> **Hard rule.** A drag handle must set `user-select: none` (and
> `touch-action: none`). Without it, pressing the handle starts a text
> selection that fights the pointer for the rest of the gesture — which does
> not look like a selection bug, it looks like dragging is sticking.

> **Hard rule.** `react-grid-layout` positions its items with `transform`.
> An animation that touches `transform` must never sit on the grid item
> itself: with `animation-fill-mode: both`, the keyframes' final
> `transform: none` wins over the inline grid transform and every block piles
> up in the top-left corner. The entrance animation lives on an element
> *inside* the item, and `globals.css` carries a
> `.react-grid-item.block-settle { animation: none }` guard so the mistake
> cannot come back silently.

`prefers-reduced-motion: reduce` collapses every animation and transition to
0.01ms.

**Arranging is not mouse-only.** The block header is focusable and carries its
own instructions as an accessible name; arrow keys move the block, shift and
arrow keys resize it, both writing through the same save path as a drag, and
the result is announced in a live region. Inputs inside a block stop
propagation so their own arrow keys still work.

---

## 8. Charts

Plotly is **bundled** (`plotly.js-dist-min`, imported lazily), not loaded from
`cdn.plot.ly`. The CDN script broke the local-only claim on every chart and
pinned the browser to a Plotly older than the one producing the figures.

The model writes whatever Plotly it likes, so `components/plot.tsx` re-themes
every figure on the way in. What we override:

- `colorway` → our series, plus a per-trace swap of Plotly's own default
  palette (see §2); transparent paper and plot backgrounds
- our font and `--body` as the default text colour
- axes: `--surface-sunken` gridlines, `--hairline` zero and axis lines,
  `--muted` 11px ticks, `automargin`
- legend → horizontal, above the plot, left-aligned
- the figure's own `title` is dropped — the block header already names it
- bars get `marker.cornerradius: "50%"` — a percentage gives a true capsule at
  any bar width, where a fixed radius only rounds the corners
- lines get `spline`, width 3.25; the round caps are set in `globals.css`
  (`stroke-linecap: round` on `.scatterlayer`), because Plotly exposes no
  line-cap option on scatter traces
- hover label: white, hairline border, ink text

What we leave alone: the data, the trace types, the value formats, the axis
titles. Re-theming is not re-authoring.

**Numbers are formatted here, not by the model.** A 9B model will not reliably
remember d3 format strings, and a KPI that prints `583271495.17` has failed at
the one job a KPI has. So every figure, from every model, gets:

- thousands separators on a headline number, and the number in full — a
  deliberate format the model chose is kept, but an SI one is not (`.0s`
  renders 72,466 as "72k") and neither is a string that is not a d3 format at
  all, which Plotly ignores in silence
- the value above each bar, up to twelve bars, where the model did not label
  them itself — reading a bar against a gridline is a guess
- the currency, on the axis that holds the money

**The currency comes from the data, never from a guess.** A field named
`mrrUsd` or an axis titled "Revenue (EUR)" names its currency; `salePrice`
does not, and printing a dollar sign on it would be a wrong number rather than
a prettier one. Where nothing is named, `NEXT_PUBLIC_DEFAULT_CURRENCY` lets the
operator assert one once (AED, USD, a symbol); unset means separators and no
symbol. It is applied only to money-ish measures, so a count of orders stays a
count.

Not taken from the reference: its vertical gradient fills on bars. Plotly has
no gradient fill for a bar trace, and the ways of faking one (per-point colour
ramps, overlaid shapes) break as soon as the data changes. The flat series
colour is the honest version.

**KPI tiles.** A Plotly `indicator` trace *is* a stat card — one big number,
no axes. The backend detects an all-`indicator` figure, stores it as a
`metric` block at tile size, and titles the block with the label the model
wrote rather than the sentence the user typed. The front end drops the
in-figure title, hides the legend, shrinks the margins to 8–12px and sets the
number in Outfit/`--ink`. **No font size is set on the number**: Plotly then
scales it to the tile, which is what a block you can drag-resize needs.

---

## 9. Notes, naming and saving

**Blocks are titled by the model.** A block used to be titled with the
sentence the user typed, so a canvas read "Bar chart counting report blocks by
kind". The narrator writes a short name for what the chart shows; a KPI keeps
the label its own figure declares. The data source is not repeated under the
title — the report header already says what this report reads.

**Notes are formatted text.** A note block is a contenteditable with a small
toolbar — bold, italic, underline, heading, bulleted and numbered list, clear
formatting — so bold text looks bold while you write it rather than looking
like `**bold**`. The editor is deliberately *uncontrolled*: React owns the
value at mount and at blur, the browser owns it in between. Writing the value
back on every keystroke is what makes a contenteditable throw the caret to the
start of the line.

Fourteen tags are allowed and **no attribute at all** except a validated
`href` (`https:`, `http:` or `mailto:`, rewritten with `rel="noreferrer
noopener"`). `lib/rich-text.ts` sanitises on the way in *and* on the way out:
on commit, so what is stored is clean, and on render, because a stored body
arrives from the database, which is not the same trust boundary as the tab
that wrote it. A paste goes through the same filter, so a note can pick up
bold and lists from the clipboard and nothing else. The sanitiser is a
tokeniser over an allowlist rather than a DOM pass, so it answers identically
during server rendering, where `DOMParser` does not exist.

Rendered notes get their own small type scale under `.rich-text` — a note is a
caption on a dashboard, not an article.

**The report name is edited in place.** Click the title, and the old name is
selected so typing replaces it; Enter commits, Escape reverts (the field
unmounts, so no blur fires and nothing is written). A rename has to reach the
sidebar, which did not make the request, so `lib/reports.ts` announces it on a
window event — the same shape as the session store.

**Saving is visible.** Every write on the canvas goes through one tracker, so
the header always says which of *saving / all changes saved · HH:MM / last
change could not be saved* is true, in a live region. The Save button is the
explicit version of the same write: it blurs whatever is being edited so that
editor commits, then writes the name and the layout. It is a real write, not a
reassurance — a button that only said "Saved" would be a lie.

## 10. Export

`lib/export-pdf.ts`. **The app builds the PDF and hands over the file.** Export
used to be `window.print()`, so the deliverable came out of the browser's print
dialog — its margins, its header and footer, and a "Save as PDF" step in the
middle of what should be one click. The app was asking Chrome to produce its
output and had no say in the result.

A4 landscape, because a 12-column dashboard is a wide thing. Blocks land at
their real `x/y/w/h`: the arrangement is the user's work, and an export that
stacks everything into one column is discarding it.

**Charts are re-rendered, never screenshotted.** Every block is a live Plotly
graph div, so `Plotly.toImage` lays the figure out *for the printed box* —
axes, ticks and legend sized for that rectangle. html2canvas would give a
stretched bitmap, lose SVG text, and add a second renderer to keep in step with
`plot.tsx`. jsPDF is lazy-imported inside the click handler, the same way
`plot.tsx` imports Plotly, so it stays out of the initial bundle. It makes no
network request: the local-only rule is about runtime requests, not about npm.

> **Row height comes from the page, not from the screen.** Mapping the canvas
> 1:1 (a 1100px canvas onto a 273mm page) makes a row 10.9mm and preserves
> every block's on-screen aspect ratio — and is wrong. A default 9-row chart
> then eats 130mm of a 153mm page, so every block lands on a page of its own:
> a five-block report measured **five** mostly-empty pages. A screen scrolls
> and a page does not, so they cannot share a row height. The rule instead: a
> 9-row chart takes 60% of a page's content height. The same report is now
> three pages. Blocks come out wider than tall, which is the right shape for a
> landscape page, and since Plotly relays the figure out for that box rather
> than stretching it, nothing is distorted.

> **Hard rule.** The figure font is `var(--font-jakarta)`, and `toImage`
> renders into a detached tree where that custom property does not resolve — so
> every exported chart came out in the browser's serif default while the rest
> of the PDF was sans. The export reads the real family names off those
> variables and substitutes them into a *copy* of the figure. Read them from
> `document.body`, not `document.documentElement`: `next/font` declares them on
> the body, and `:root` returns empty, which fails silently back to a generic
> face.

Pagination: blocks sorted by `(y, x)`; when one would cross the page bottom, a
new page starts at that block's row, so blocks sharing rows stay side by side
and none is ever sliced. A block taller than a whole page is clamped — with
~7.7mm rows that is reachable, since the canvas lets a block be resized past
a page.

Notes are drawn as real text, not pictures of text, so an exported note stays
selectable and searchable. The 14-tag allowlist is parsed into headings,
paragraphs and lists, and inline `strong`/`em` survive as styled runs with
manual word wrapping rather than being flattened to one style.

On paper each block carries a hairline border. On screen this system separates
surfaces by value and bans decorative borders — but a white card on white paper
is invisible, so the hairline is the print equivalent of that value step, not
decoration.

The `@media print` rules below remain so ⌘P still produces something sane, but
they are no longer the Export path. They drop the sidebar and every
`print:hidden` control, flatten the absolutely-positioned grid into a stacked
document, and release the shell's scroll regions
(`overflow: visible; height: auto`) so the whole report reaches the page rather
than the slice that was on screen. Plotly writes explicit `width`/`height` onto
its SVG from the last on-screen layout, so `components/plot.tsx` re-measures
every figure on `beforeprint`, on the `matchMedia("print")` change, and again
on `afterprint`.

---

## 11. The floor

- Text never goes below `--muted`. Hairline is not a text colour.
- Every icon-only control has an `aria-label` and a `title`.
- Focus is visible everywhere: 2px `--pine`, 2px offset, via
  `:focus-visible`.
- Selection, caret, `accent-color` and scrollbars are themed. The parts not
  drawn by hand still belong to the design.
- No horizontal scroll at 375px. Verified at 375, 768 and 1440 by measuring
  `scrollWidth` against `clientWidth`, not by eye.
- Anything draggable is also keyboard-operable, and says so in its accessible
  name.
- A control that is hidden is also out of the tab order. The closed mobile
  drawer uses `visibility: hidden`, not just a transform, or a keyboard user
  tabs through an invisible sidebar before reaching the page.
- One focus treatment per control, decided on purpose. Composing a
  `focus:ring-*` utility with `focus:ring-0` leaves it to CSS source order
  whether the control shows focus at all.
- No eyebrow labels. The reference uses them above every card title; they are
  banned here and no brief earns them back.
