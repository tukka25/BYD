# PromptDash — design system

Derived from the shipped build, not from intentions. Every value below is one
you can find in the code; where a number was measured (contrast, size) the
measurement is given rather than an adjective.

Surface mode: **Operate**. The visitor is here to finish a task — ask a
question, read the answer, arrange a report. Brand lives in precision, not in
expression. Scanability and native expectations outrank personality.

Binding reference: `design/references/02-violet-amber-console.webp`.
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
| `--violet` | `#5b3df5` | The one accent. 5.3:1 as text on canvas; takes white text at 6.1:1. Primary buttons, active state, focus ring, caret, selection, series 1. |
| `--violet-wash` | `#eeeaff` | Active nav, chips, the avatar disc. |
| `--amber` | `#f5a524` | Fills only. Carries `--ink` at 9.2:1, never white. |
| `--coral` | `#f2563f` | Fills and destructive. White text only above ~18px (3.4:1). |
| `--teal` | `#0e9e8e` | The "runs on this machine" mark, positive deltas. |

Each has a `-wash` tint for chip and alert backgrounds. Alert text uses the
darkened pairs `#b5301c` (coral), `#8a5a00` (amber), `#0a6b60` (teal) so a
badge still reads at 12px.

### Chart series

```
1 #5b3df5   2 #f5a524   3 #f2563f   4 #0e9e8e
5 #9b5cf6   6 #2b7fff   7 #d9479b   8 #7a8699
```

Violet, amber and coral lead so a chart looks like the rest of the app on
sight; 5–8 extend without colliding in hue. This order is applied as Plotly's
`colorway` in `components/plot.tsx`, so the model's own colour choices are
overridden on every figure.

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
--lift-drag  0 8px 16px / 0.10, 0 24px 56px violet/0.18   a block being dragged
```

A block picks up `--lift-drag` while it is dragged or resized, so the thing in
your hand is unambiguous.

---

## 5. Components (`components/ui.tsx`)

Every control in the app is built from these. A stock `<button>` or `<input>`
never appears inside a committed surface.

- **Panel** — `rounded-[24px] bg-surface shadow-[--lift-1]`. No border.
- **Button** — variants `primary` (violet/white), `secondary` (white with a
  hairline inset ring), `ghost`, `danger`. Sizes `sm` 32px / `md` 40px /
  `lg` 48px. `active:translate-y-px`; disabled drops to 45% and loses pointer
  events.
- **IconButton** — a 36px circle, `--muted` at rest, tinting to `--ink` (or
  coral for `tone="danger"`) on hover. Always carries `aria-label` and
  `title`; this is the only control that ships without a visible label.
- **Chip** — pill, 12px semibold, five tones, each a wash with its darkened
  text pair.
- **Segmented** — `role="tablist"`, a sunken track with a white lifted pill on
  the active option. Used for Edit / View.
- **Field** + `inputClass` — 44px tall, hairline inset ring, focus swaps to a
  2px violet ring. Label 13px semibold ink above, hint 12px muted below.
- **EmptyState** — washed icon tile, 18px heading, muted body capped at
  `max-w-sm`, one action.

**Icons** are lucide-react at **`strokeWidth={2.25}`**, everywhere. Two
exceptions, both deliberate: the wordmark mark (2.75 — it is a logo, not an
icon) and the 13px tick inside a filled checkbox (3 — it disappears at 2.25).
A third weight is a bug, not a judgement call.

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

The ask bar is the last child of the canvas column, capped at `max-w-3xl`. It
is not a floating action button and not a fixed overlay: it is how every block
on the canvas gets made, so it stays in one place, always visible, with the
grid scrolling above it.

---

## 7. Motion

One authored moment: a block arrives on the canvas and settles into place —
`block-settle`, 520ms on `--ease-out` (`cubic-bezier(.16,1,.3,1)`), from
`translateY(10px) scale(.985) blur(6px)`. Everything else is a state change:
150ms on colour, 200ms on the segmented pill, 300ms on the drawer.

Generation takes 13–15s, so the wait is a real state and gets `.generating` —
a violet-tinted sweep across a sunken bar — rather than a spinner.

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

- `colorway` → our series; transparent paper and plot backgrounds
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

## 9. Export

Export is print-to-PDF. No dependency, works offline, and gives the user the
paper size and margins their OS already offers. `@media print` drops the
sidebar and every `print:hidden` control, flattens the absolutely-positioned
grid into a stacked document in reading order, gives each block
`break-inside: avoid`, and removes every shadow, and it releases the shell's
scroll regions (`overflow: visible; height: auto`) so the whole report reaches
the page rather than the slice that was on screen. A drag grid means nothing
on paper.

Plotly writes explicit `width`/`height` onto its SVG from the last on-screen
layout, and print styles resize the block but not the drawing inside it, so
`components/plot.tsx` re-measures every figure on `beforeprint`, on the
`matchMedia("print")` change, and again on `afterprint`.

---

## 10. The floor

- Text never goes below `--muted`. Hairline is not a text colour.
- Every icon-only control has an `aria-label` and a `title`.
- Focus is visible everywhere: 2px `--violet`, 2px offset, via
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
