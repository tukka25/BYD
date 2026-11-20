# Visual references

Two references, supplied by the user. **Reference 02 is the binding direction.**
Reference 01 is kept for its information architecture only.

---

## 01 — "Gilded Admin" (`01-gilded-admin.webp`)

**Take from it: structure only.**

- A persistent left sidebar carrying the real navigation, with a `DASHBOARD`
  group holding many named reports and a separate `COMPONENTS` group below.
  This is the IA the user asked for: multiple reports living under Dashboard.
- A top bar with search, and a KPI strip above the chart grid.
- One state in the KPI strip is inverted (dark card among light ones) to mark
  the active or primary metric.

**Do not take: its look.** The user called the current UI ugly and this template
is close to it — boxy cards, hairline borders everywhere, a cramped 4px radius,
default blue/red chart colours, flat tabular density. It is an anti-reference for
surface treatment.

---

## 02 — Violet / amber analytics console (`02-violet-amber-console.webp`, binding)

Supplied in-chat and described by the user as "very nice". The image sits beside
this note; the reading below is what was actually taken from it.

### What makes it work

**Air.** The canvas is a light neutral grey and the cards are near-white, so
cards read as raised by value alone — no heavy borders, no drop shadows doing the
work. Padding inside cards is generous; nothing is crowded.

**A two-colour signature with one alarm colour.** Violet and amber carry almost
everything, with coral reserved for a third series or a negative. Three hues,
used confidently, instead of a default categorical palette.

**Soft geometry.** Card radius is large (~24px). Bars have fully rounded caps —
pills, not rectangles — and carry a vertical gradient plus a soft outer glow.
Line strokes are thick (~4px) with round caps and no markers except at called-out
points.

**KPIs are not cards.** The metric row sits directly on the canvas: small grey
label, very large bold number, and a small grey pill beside it carrying a
secondary fact ("20 Closed", "40 Open"). Boxing them would add four more borders
and say nothing.

**Pills for state.** Segmented controls ("Monthly / Annual") are a grey track
with a filled pill for the active option. Nav tabs use the same idea — a rounded
container with a white pill behind the active tab. Filters are outlined pill
buttons with a leading icon and a trailing chevron.

**Every card has an affordance.** A small circular ↗ button sits top-right of
each panel. Each card also carries a small grey eyebrow label above its title
("Weekly Analytics" / "Customers") — a category, then a name.

**AI is a first-class surface.** A floating assistant card ("Can I help you?")
with suggestion chips and an "Ask something to AI" input, plus a sparkle-marked
search field. Worth mirroring: in this product the AI is the primary input, not a
bolt-on.

**Typography.** A geometric sans with near-circular bowls and generous
x-height — Poppins / Outfit / General Sans family. Headings are very large and
heavy with tight tracking; numbers are heavier still. Labels are small, grey, and
plainly subordinate.

### Tokens to derive

| Role | Reading |
|---|---|
| Canvas | light neutral grey, around `#EFEFF1` |
| Surface | near-white, around `#FAFAFA`–`#FFFFFF` |
| Radius | ~24px cards, ~12–14px controls, full for pills |
| Primary | vivid violet, around `#6C4CF1` |
| Accent | amber, around `#FFC83D` |
| Alert / third series | coral, around `#FF5A45` |
| Heading text | near-black, around `#0E0E10` |
| Muted text | grey, around `#8A8A8E` |
| Elevation | value contrast first; shadows barely present |

### What does not transfer

- Its data is invented. This product shows only charts that actually executed
  against the user's file, so no decorative numbers.
- It is a read-only console. Ours is an editable canvas — blocks move and resize,
  which needs grab affordances and an edit/view distinction the reference has no
  reason to show.
- The floating assistant overlaps a chart. Here the AI input is the main path to
  creating a block and should have a stable home, not float over content.

### Hard constraint from PRODUCT.md

**Fully local, no cloud.** Whatever typeface is chosen ships from this repo. No
Google Fonts link, no CDN. The same applies to Plotly, currently loaded from
`cdn.plot.ly` and in breach.
