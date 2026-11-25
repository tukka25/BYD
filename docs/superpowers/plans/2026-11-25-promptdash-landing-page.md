# PromptDash Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static landing page for PromptDash in `site/`, deployed by Vercel, that tells how the chartist was fine-tuned, quotes only checked numbers, and shows three dashboards the app drew, each with the prompt that drew it.

**Architecture:** Two byd-web components give up their pure parts to `byd-web/lib/` (the dot animation and the chart re-theme), so the site can carry byte-identical copies. `backend/scripts/make_showcase.py` builds each dashboard through the running app's HTTP API, the way a person does, and exports the saved blocks unedited to `site/data/dashboards/`. `site/` is a separate Next.js 16 app with `output: "export"`. Every number it shows is in `site/data/stats.json`, and `npm test` checks each one against the file that recorded it.

**Tech Stack:** Next.js 16.1.6 (App Router, static export, Turbopack), React 19.2.3, Tailwind CSS 4, TypeScript 5, plotly.js-dist-min 4.3.0, Node 24's built-in test runner (it strips TypeScript itself); Python 3.13 standard library (`urllib`) for the scripts, pandas + openpyxl for the Excel file, psycopg2 for one row count; pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-promptdash-landing-page-design.md`

## Global Constraints

- Work in the main checkout, `/Users/atukka/Desktop/BYD`, on branch `feat/landing-page`, not in a worktree. The showcase needs the running stack (containers `promptdash-api`, `promptdash-postgres`, `promptdash-web`), the model server (`make serve-model`, 127.0.0.1:8080, lora-v2) and gitignored files (`backend/uploads/`, `chartist-finetune/models/`, the venvs).
- byd-web on :3000 hot-reloads this checkout's `byd-web/app`, `lib` and `components`. Every byd-web commit leaves the app working.
- A number with no recorded source does not go on the page.
- Charts are never edited. When a dashboard falls short, the prompt changes the way a user would rephrase it, and the dashboard is built again. No hardcoded charts: every chart on the page is the app's unedited output.
- Downloads need the owner's OK first, with each file's name, source and size.
- Never rebuild or restart a Docker container, push a branch, or create the Vercel project without the owner's OK.
- Never print, log or commit a secret: `CLAUDE_API_KEY`, the Postgres password, the showcase account's password, access tokens.
- Never modify or train on `chartist-finetune/data/testset.jsonl` (sha256 `bf385c59…`) or the planning test set.
- Commit each task when it is done. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Name: PromptDash. Credit: @tukka25 on GitHub. Repository link: `https://github.com/tukka25/BYD` (part 2 renames it).
- Page text is short and technical. Light theme only, like the app. Visual language: `byd-web/DESIGN.md`.
- Pinned versions in `site/`: next 16.1.6, react and react-dom 19.2.3, plotly.js-dist-min 4.3.0, eslint-config-next 16.1.6; tailwindcss and @tailwindcss/postcss ^4; typescript ^5; eslint ^9; @types/node ^20; @types/react and @types/react-dom ^19.
- `lib/` files use explicit relative `.ts` imports (`./dot-shapes.ts`), never the `@/` alias: Node's test runner loads them directly.
- The four copies in `site/lib/` (`dot-shapes.ts`, `dot-draw.ts`, `plot-theme.ts`, `rich-text.ts`) are byte-identical to byd-web's. Change byd-web's original, then copy it (`npm run sync-lib` in `site/`).
- Each dashboard file is under 1,500,000 bytes.
- Steps marked **(controller)** browse, use the model, or ask the owner. A subagent does not run them.
- Run tests from each project's folder: `cd byd-web && npm test`; `cd site && npm test`; `cd backend && .venv/bin/python -m pytest -q tests/<file>`.

## Files

| Path | Responsibility |
|---|---|
| `byd-web/lib/dot-draw.ts` (new) | One frame of the dot animation (`drawDots`) and the canvas lifecycle (`animateDots`) |
| `byd-web/lib/plot-theme.ts` (new) | The chart re-theme (`themed`), moved out of `components/plot.tsx` |
| `byd-web/components/build-loader.tsx`, `byd-web/components/plot.tsx` | Call the moved code |
| `backend/scripts/fetch_showcase_data.py` (new) | Downloads the file sources, saves listings as Excel, writes a manifest |
| `backend/scripts/make_showcase.py` (new) | Builds one dashboard through the app's API and exports it |
| `Makefile` | Target `showcase` |
| `site/` (new) | The landing page: configs, `app/`, `components/`, `lib/`, `data/`, `tests/`, `README.md`, `vercel.json` |

## Shared formats

### Dashboard file: `site/data/dashboards/<name>.json`

Written by `make_showcase.py` (Task 5), read by the site (Task 10). Compact JSON. The values below are examples.

```json
{
  "name": "airbnb",
  "title": "Airbnb in Edinburgh",
  "prompt": "thinking of renting out my flat in edinburgh on airbnb. which areas charge the most, entire place vs private room, and when are guests busiest?",
  "currency": "GBP",
  "sources": [
    {"name": "listings.xlsx", "kind": "file", "rows": 5123,
     "url": "https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/2025-09-21/visualisations/listings.csv",
     "licence": "CC BY 4.0", "licence_url": "https://creativecommons.org/licenses/by/4.0/",
     "note": "Inside Airbnb, Edinburgh, snapshot 2025-09-21. Saved as Excel from the published CSV."}
  ],
  "blocks": [
    {"kind": "text", "title": "About this data", "chart_type": null, "figure": null,
     "text_body": "<p>...</p>", "code": null, "x": 0, "y": 0, "w": 12, "h": 3},
    {"kind": "chart", "title": "Average price by area", "chart_type": "bar", "figure": {"data": [], "layout": {}},
     "text_body": null, "code": "import plotly.express as px\n...", "x": 0, "y": 3, "w": 6, "h": 8}
  ],
  "build": {"charts_planned": 7, "charts_drawn": 7, "skipped": [], "missing_kinds": [], "seconds": 125.4, "prompts_tried": 1},
  "model": {"base": "models/qwen3.5-9b-4bit", "adapter": "runs/adapters-mlx-v2", "label": "lora-v2"},
  "app_commit": "c416ee1",
  "generated_at": "2026-11-26T09:30:00Z"
}
```

- `kind` is `text`, `chart` or `metric`. A metric is an all-indicator figure, as the app stores it.
- `chart` and `metric` blocks have a `figure` with a `data` array. `text` blocks have `text_body`.
- `x >= 0`, `y >= 0`, `w >= 1`, `h >= 1`, `x + w <= 12`. Blocks are sorted by `y`, then `x`.
- `build.charts_planned` is the `plan` event's `total` minus 1, because the total counts the intro text block. `build.charts_drawn` counts the `chart` and `metric` blocks. `build.skipped` lists the `skipped` events as `{"label", "reason"}`.
- `model.label` is `lora-v2` only when the model server runs with `--adapter-path runs/adapters-mlx-v2`; otherwise it is the adapter path itself.
- `app_commit` ends in `-dirty` when `backend/app` had uncommitted changes during the build.

### Numbers: `site/data/stats.json`

Written in Task 8, formatted by `site/lib/stats.ts`. One entry:

```json
{"id": "v2_render_mac", "value": 0.9433, "format": {"kind": "percent", "decimals": 1},
 "label": "lora-v2 chart scripts that run, frozen 300, 4-bit on a Mac",
 "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_v2.json", "path": ["lora-v2", "render_rate"]}}
```

- `value` is the raw number from the source. The page formats it and may ask for fewer decimals: the hero shows `94%` from this same entry.
- `format.kind`: `percent` (a fraction, shown ×100 with `%`), `usd` (`$` and grouping), `number` (grouping), `duration` (seconds shown as `2 h 24 m`).
- `source.kind`:
  - `json`: the value at `path` in `file` equals `value` exactly.
  - `quote`: `file` contains `quote` (runs of whitespace collapsed on both sides), and `quote` contains the formatted value.
  - `sum`: `value` equals the sum of the values of the entries named in `of`.

---

### Task 1: Licences and the owner's OK for the downloads (controller)

Nothing here is code. It produces values that Tasks 4 and 5 use, recorded in the ledger.

**Files:** none.

- [ ] **Step 1: Inside Airbnb.** Open https://insideairbnb.com/get-the-data/ in the browser pane. In the "Edinburgh, Scotland, United Kingdom" table, note the latest snapshot date and the links to `listings.csv` and `reviews.csv` under "visualisations" (the summary files). They should read `https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/<YYYY-MM-DD>/visualisations/listings.csv` and `.../reviews.csv`. Find the site's licence statement (expected: Creative Commons Attribution 4.0 International) and note the page it is on.
- [ ] **Step 2: Netflix.** Open https://github.com/rfordatascience/tidytuesday/tree/main/data/2021/2021-04-20 and read the readme: the source (Kaggle, "Netflix Movies and TV Shows" by Shivam Bansal) and any licence. Then open https://www.kaggle.com/datasets/shivamb/netflix-shows and read the licence on the page. If the page needs a login, use what the TidyTuesday readme states and say that you did. The file is `https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2021/2021-04-20/netflix_titles.csv`.
- [ ] **Step 3: Spotify.** No download: the `spotify` database already holds `tracks` (32,833 rows). Open https://github.com/rfordatascience/tidytuesday/tree/main/data/2020/2020-01-21 and note the source (the `spotifyr` package, from the Spotify Web API) and any licence. Then read what Spotify's Developer Terms (https://developer.spotify.com/terms) say about showing that data. Decide:
  - **keep Spotify**, with the licence line to print; or
  - **switch to the shop demo** (`shop` database, synthetic, built by `backend/scripts/make_relational_demo.py`; it also shows the app joining tables).

  If the terms are unclear, recommend the shop demo.
- [ ] **Step 4: Sizes, without downloading:** `curl -sIL <url> | grep -i '^content-length'` for each of the three files.
- [ ] **Step 5: Ask the owner in one message:** each file's name, source URL and size, each licence with its link, and the Spotify decision. Wait for a clear yes. Anything the owner changes overrides the defaults below.
- [ ] **Step 6: Record in the ledger:** the Airbnb snapshot date, the three URLs, each licence and its URL, and the Spotify decision. Where a recorded value differs from a constant in Task 4's or Task 5's code, that task's implementer uses the recorded value.

---

### Task 2: Move the dot animation's canvas code into `byd-web/lib/dot-draw.ts`

The build loader's canvas code moves to `lib/`, so the hero (Task 9) runs the same code from a byte-identical copy instead of a lookalike. The loader must look and behave exactly as before.

**Files:**
- Create: `byd-web/lib/dot-draw.ts`
- Modify: `byd-web/components/build-loader.tsx`
- Modify: `byd-web/DESIGN.md` (one file reference)
- Test: `byd-web/tests/dot-draw.test.mts`

**Interfaces:**
- Consumes: `byd-web/lib/dot-shapes.ts`, unchanged: `DOTS`, `SHAPE_POINTS`, `dotAt(a, b, progress, index)`, `frameAt(ms)`, `type ShapeName`.
- Produces:
  - `type DotFrame = { width: number; height: number; elapsed: number; reduced: boolean; color: string }`
  - `type DotContext = Pick<CanvasRenderingContext2D, "clearRect" | "beginPath" | "arc" | "fill" | "fillStyle" | "globalAlpha">`
  - `drawDots(context: DotContext, frame: DotFrame): void`: one frame.
  - `type DotOptions = { logicalWidth?: number }`
  - `animateDots(node: HTMLCanvasElement, options?: DotOptions): () => void`: owns the canvas. It sizes it for the device pixel ratio, draws the first frame at once, loops on `requestAnimationFrame` while the canvas is on screen, holds the still line under reduced motion, and returns the function that stops it. With `logicalWidth`, it draws as if the canvas were that many CSS pixels wide and scales the result, so the dots grow with a bigger canvas.

- [ ] **Step 1: Write the failing test** `byd-web/tests/dot-draw.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { SHAPE_POINTS } from "../lib/dot-shapes.ts";
import { drawDots, type DotContext } from "../lib/dot-draw.ts";

type Arc = { x: number; y: number; r: number; alpha: number; fill: string };

function recorder() {
  const arcs: Arc[] = [];
  const cleared: number[][] = [];
  const context: DotContext = {
    fillStyle: "",
    globalAlpha: 1,
    clearRect: (x, y, w, h) => {
      cleared.push([x, y, w, h]);
    },
    beginPath: () => {},
    arc: (x, y, r) => {
      arcs.push({ x, y, r, alpha: context.globalAlpha, fill: String(context.fillStyle) });
    },
    fill: () => {},
  };
  return { context, arcs, cleared };
}

const shownIn = (name: keyof typeof SHAPE_POINTS) => SHAPE_POINTS[name].filter((p) => p.weight > 0).length;

test("the first frame clears the canvas and draws the line's dots in the given colour", () => {
  const { context, arcs, cleared } = recorder();
  drawDots(context, { width: 500, height: 300, elapsed: 0, reduced: false, color: "#176b4e" });
  assert.deepEqual(cleared, [[0, 0, 500, 300]]);
  assert.equal(arcs.length, shownIn("line"));
  assert.ok(arcs.every((arc) => arc.fill === "#176b4e"));
  assert.equal(context.globalAlpha, 1);
});

test("every dot sits inside the 8% padding of the frame", () => {
  const { context, arcs } = recorder();
  drawDots(context, { width: 500, height: 300, elapsed: 1234, reduced: false, color: "#000" });
  assert.ok(arcs.length > 0);
  for (const arc of arcs) {
    assert.ok(arc.x >= 40 - 1e-9 && arc.x <= 460 + 1e-9, `x ${arc.x}`);
    assert.ok(arc.y >= 24 - 1e-9 && arc.y <= 276 + 1e-9, `y ${arc.y}`);
  }
});

test("with reduced motion the line holds still, whatever the clock says", () => {
  const first = recorder();
  const later = recorder();
  drawDots(first.context, { width: 320, height: 192, elapsed: 0, reduced: true, color: "#000" });
  drawDots(later.context, { width: 320, height: 192, elapsed: 98_765, reduced: true, color: "#000" });
  assert.deepEqual(first.arcs, later.arcs);
  assert.equal(first.arcs.length, shownIn("line"));
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd byd-web && npm test`
Expected: FAIL in `dot-draw.test.mts` with `Cannot find module '.../lib/dot-draw.ts'`. The other test files pass.

- [ ] **Step 3: Create `byd-web/lib/dot-draw.ts`.** The drawing and the lifecycle are the code now inside `BuildLoader`'s third `useEffect`, unchanged apart from `logicalWidth`:

```ts
import { DOTS, SHAPE_POINTS, dotAt, frameAt, type ShapeName } from "./dot-shapes.ts";

/* The dot animation on a canvas: the build loader's (components/build-loader.tsx)
   and, through a byte-identical copy, the landing page's hero
   (site/lib/dot-draw.ts, checked by site/tests/copies.test.mts).

   drawDots draws one frame and touches only the context it is given, so a
   test can run it without a browser. animateDots owns the canvas: it sizes it
   for the device pixel ratio, draws the first frame at once (an empty box is
   not a loading state), loops while the canvas is on screen and stops when the
   function it returns is called. One canvas and 36 dots, like DotWave:
   animating DOM nodes would be a style write per dot per frame.
   requestAnimationFrame does not fire in a hidden tab, so a hidden tab pauses
   it too. */

const STILL = { from: "line" as ShapeName, to: "line" as ShapeName, progress: 0 };

export type DotFrame = { width: number; height: number; elapsed: number; reduced: boolean; color: string };

export type DotContext = Pick<
  CanvasRenderingContext2D,
  "clearRect" | "beginPath" | "arc" | "fill" | "fillStyle" | "globalAlpha"
>;

export function drawDots(context: DotContext, { width, height, elapsed, reduced, color }: DotFrame): void {
  const { from, to, progress } = reduced ? STILL : frameAt(elapsed);
  const a = SHAPE_POINTS[from];
  const b = SHAPE_POINTS[to];
  // Padding in proportion, so the drawing area keeps the 5:3 frame the
  // shapes were laid out for and the grid stays square.
  const padX = width * 0.08;
  const padY = height * 0.08;
  const t = elapsed / 1000;

  context.clearRect(0, 0, width, height);
  context.fillStyle = color;
  for (let i = 0; i < DOTS; i += 1) {
    const p = dotAt(a[i], b[i], progress, i);
    // A dot a shape does not use sits at weight 0, so it fades out and
    // shrinks on the way to its parking spot and back on the way out.
    const shown = Math.min(1, p.weight / 0.25);
    if (shown <= 0) continue;
    // A slow brightness wave across the frame keeps a held shape alive.
    const pulse = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(t * 2.2 - p.x * 7);
    context.globalAlpha = shown * Math.min(1, 0.3 + 0.55 * p.weight + 0.15 * pulse);
    context.beginPath();
    context.arc(
      padX + p.x * (width - 2 * padX),
      padY + p.y * (height - 2 * padY),
      (1.6 + 1.9 * p.weight + 0.35 * pulse) * (0.4 + 0.6 * shown),
      0,
      Math.PI * 2,
    );
    context.fill();
  }
  context.globalAlpha = 1;
}

export type DotOptions = {
  /* Draw as if the canvas were this many CSS pixels wide, then scale, so the
     dots grow with a bigger canvas instead of thinning out. Unset, the
     drawing uses the canvas's own size, as the build loader does. */
  logicalWidth?: number;
};

export function animateDots(node: HTMLCanvasElement, { logicalWidth }: DotOptions = {}): () => void {
  const context = node.getContext("2d");
  if (!context) return () => {};

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const color = getComputedStyle(document.documentElement).getPropertyValue("--pine").trim() || "#176b4e";
  let width = 0;
  let height = 0;
  let frame = 0;
  let origin = -1;
  let running = false;

  const resize = () => {
    const ratio = window.devicePixelRatio || 1;
    const rect = node.getBoundingClientRect();
    const cssWidth = Math.max(1, Math.floor(rect.width));
    const cssHeight = Math.max(1, Math.floor(rect.height));
    const scale = logicalWidth ? cssWidth / logicalWidth : 1;
    width = cssWidth / scale;
    height = cssHeight / scale;
    node.width = Math.floor(cssWidth * ratio);
    node.height = Math.floor(cssHeight * ratio);
    context.setTransform(ratio * scale, 0, 0, ratio * scale, 0, 0);
  };

  const draw = (time: number) => {
    if (origin < 0) origin = time;
    drawDots(context, { width, height, elapsed: time - origin, reduced, color });
  };

  const loop = (time: number) => {
    draw(time);
    frame = requestAnimationFrame(loop);
  };
  const play = () => {
    if (reduced || running) return;
    running = true;
    frame = requestAnimationFrame(loop);
  };
  const pause = () => {
    running = false;
    cancelAnimationFrame(frame);
  };

  resize();
  draw(performance.now());
  play();

  const sizes = new ResizeObserver(() => {
    resize();
    draw(performance.now());
  });
  sizes.observe(node);
  const seen = new IntersectionObserver(([entry]) => (entry?.isIntersecting ? play() : pause()));
  seen.observe(node);

  return () => {
    pause();
    sizes.disconnect();
    seen.disconnect();
  };
}
```

- [ ] **Step 4: Make `BuildLoader` call it.** In `byd-web/components/build-loader.tsx`:

  1. Replace the import line `import { DOTS, SHAPE_POINTS, dotAt, frameAt, type ShapeName } from "@/lib/dot-shapes";` with:

  ```ts
  import { animateDots } from "@/lib/dot-draw";
  ```

  2. In the top comment, replace its last paragraph (from `One canvas and 36 dots, like \`DotWave\`` to `pauses while it is off screen. */`) with:

  ```ts
     The canvas is drawn by lib/dot-draw.ts, which the landing page's hero
     shares: one canvas and 36 dots, the first frame drawn at once, paused
     while it is off screen. */
  ```

  3. Delete the line `const STILL = { from: "line" as ShapeName, to: "line" as ShapeName, progress: 0 };`.

  4. Replace the whole third `useEffect` (the one that starts `const node = canvas.current;` and ends with `seen.disconnect();\n    };\n  }, []);`) with:

  ```tsx
    useEffect(() => {
      const node = canvas.current;
      if (!node) return;
      return animateDots(node);
    }, []);
  ```

  The JSX, the `clock` helper and the first two effects stay as they are.

- [ ] **Step 5: Point DESIGN.md at the new file.** In `byd-web/DESIGN.md`, replace `` `components/build-loader.tsx`: the same pine dots `` with `` `components/build-loader.tsx` (drawn by `lib/dot-draw.ts`): the same pine dots ``.

- [ ] **Step 6: Run the checks**

Run: `cd byd-web && npm test && npm run lint && npx tsc --noEmit`
Expected: every test passes, including the 3 new ones; lint and tsc print no errors.

- [ ] **Step 7: Commit**

```bash
git add byd-web/lib/dot-draw.ts byd-web/tests/dot-draw.test.mts byd-web/components/build-loader.tsx byd-web/DESIGN.md
git commit -m "refactor(web): the dot animation's canvas code moves to lib/dot-draw.ts

BuildLoader keeps its label and timer and calls animateDots. The landing
page's hero will run a byte-identical copy, so it is the same animation,
not a lookalike. Unchanged apart from logicalWidth, which lets a bigger
canvas draw bigger dots; the loader does not pass it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Move the chart re-theme into `byd-web/lib/plot-theme.ts`

`themed` and its helpers move out of `components/plot.tsx` unchanged, so the site can carry a byte-identical copy. Its one outside input, the default currency, becomes a parameter. The read of `process.env.NEXT_PUBLIC_DEFAULT_CURRENCY` stays in `plot.tsx`, because Next inlines a `NEXT_PUBLIC_` variable only where the code names it.

**Files:**
- Create: `byd-web/lib/plot-theme.ts`
- Modify: `byd-web/components/plot.tsx`
- Modify: `byd-web/DESIGN.md`, `AGENTS.md` (file references)
- Test: `byd-web/tests/plot-theme.test.mts`

**Interfaces:**
- Produces:
  - `type PlotlyFigure = { data?: unknown[]; layout?: Record<string, unknown> }`
  - `themed(figure: PlotlyFigure, defaultCurrency = ""): { data: Record<string, unknown>[]; layout: Record<string, unknown> }`. `defaultCurrency` is a code (`GBP`, `AED`) or a literal symbol, applied only to money columns that name no currency. Empty means no symbol is invented.

- [ ] **Step 1 (controller): Screenshots before the change.** Log in to http://localhost:3000 with the throwaway live-check account (its credentials are in the controller's scratchpad; never print them). Open a report with a bar chart, a KPI and a line, and take a screenshot of the canvas.

- [ ] **Step 2: Write the failing test** `byd-web/tests/plot-theme.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { themed } from "../lib/plot-theme.ts";

function at(value: unknown, ...path: string[]): unknown {
  return path.reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], value);
}

const bars = (n: number) => ({
  type: "bar",
  x: Array.from({ length: n }, (_, i) => `c${i}`),
  y: Array.from({ length: n }, (_, i) => i),
});

test("Plotly's default trace colours become the app's series; a chosen colour stays", () => {
  const { data } = themed({
    data: [
      { ...bars(2), marker: { color: "#636efa" } },
      { ...bars(2), marker: { color: "#123456" } },
    ],
  });
  assert.equal(at(data[0], "marker", "color"), "#176b4e");
  assert.equal(at(data[1], "marker", "color"), "#123456");
});

test("the plot's own title is dropped, since the block header names the chart", () => {
  assert.equal(themed({ data: [], layout: { title: { text: "Sales" } } }).layout.title, undefined);
});

test("a money axis that names its currency gets it, and only that axis", () => {
  const { layout } = themed({
    data: [bars(3)],
    layout: { xaxis: { title: { text: "Year" } }, yaxis: { title: { text: "Revenue (EUR)" } } },
  });
  assert.equal(at(layout, "yaxis", "tickprefix"), "€");
  assert.equal(at(layout, "xaxis", "tickprefix"), undefined);
});

test("an unnamed currency is never invented; the default currency fills a money axis only", () => {
  const price = { data: [bars(3)], layout: { yaxis: { title: { text: "Price" } } } };
  const listings = { data: [bars(3)], layout: { yaxis: { title: { text: "Listings" } } } };
  assert.equal(at(themed(price).layout, "yaxis", "tickprefix"), undefined);
  assert.equal(at(themed(price, "GBP").layout, "yaxis", "tickprefix"), "£");
  assert.equal(at(themed(listings, "GBP").layout, "yaxis", "tickprefix"), undefined);
});

test("a dozen bars or fewer get their values above them; more do not", () => {
  assert.equal(at(themed({ data: [bars(12)] }).data[0], "texttemplate"), "%{y:.5~s}");
  assert.equal(at(themed({ data: [bars(13)] }).data[0], "texttemplate"), undefined);
});

test("a KPI keeps a readable format, replaces a broken one, and takes the named currency", () => {
  const kpi = (valueformat: string) => ({
    data: [{ type: "indicator", mode: "number", value: 583271495.17, number: { valueformat } }],
    layout: { title: { text: "Revenue (USD)" } },
  });
  assert.equal(at(themed(kpi("#1f77b4")).data[0], "number", "valueformat"), ",.0f");
  assert.equal(at(themed(kpi(".1%")).data[0], "number", "valueformat"), ".1%");
  assert.equal(at(themed(kpi("")).data[0], "number", "prefix"), "$");
});
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd byd-web && npm test`
Expected: FAIL in `plot-theme.test.mts` with `Cannot find module '.../lib/plot-theme.ts'`.

- [ ] **Step 4: Create `byd-web/lib/plot-theme.ts`.** Start it with this comment:

```ts
/* The chart re-theme. Every Plotly figure from every model passes through
   `themed` before it is drawn, so a chart looks like the rest of the app
   instead of Plotly's defaults, and its numbers read as numbers: separators,
   a currency the data names, values above a dozen bars or fewer.

   Moved out of components/plot.tsx unchanged, so the landing page can carry a
   byte-identical copy (site/lib/plot-theme.ts, checked by
   site/tests/copies.test.mts). Its one outside input, the default currency,
   is a parameter: plot.tsx passes NEXT_PUBLIC_DEFAULT_CURRENCY, and the
   landing page passes the currency its dashboard file states. */

```

Below it, move lines 16–329 of `byd-web/components/plot.tsx` verbatim: from `type PlotlyFigure = {` to the closing `}` of `function themed`. Check the boundaries first with `sed -n '16p;329p' byd-web/components/plot.tsx`, which must print `type PlotlyFigure = {` and `}`. Then make exactly four edits in the moved code:

  1. `type PlotlyFigure = {` becomes `export type PlotlyFigure = {`.
  2. Delete the `DEFAULT_CURRENCY` comment and constant:

  ```ts
  /* When the data names no currency, the app does not guess one -- but you can
     say which it is, once, and have every unlabelled money column use it:
     NEXT_PUBLIC_DEFAULT_CURRENCY=AED (or USD, EUR, or a literal symbol).
     Unset means numbers get their separators and no symbol. */
  const DEFAULT_CURRENCY = symbolFor(process.env.NEXT_PUBLIC_DEFAULT_CURRENCY ?? "");
  ```

  3. `detectCurrency` takes the fallback as a parameter:

  ```ts
  function detectCurrency(figure: PlotlyFigure, fallback: string): string {
    const words = figureWords(figure);
    for (const [pattern, symbol] of CURRENCIES) {
      if (pattern.test(words)) return symbol;
    }
    // Only money-ish measures take the default; a count of orders is not money.
    return MONEYISH.test(words) ? fallback : "";
  }
  ```

  4. `themed` is exported and takes the default currency:

  ```ts
  /** The figure, re-themed. `defaultCurrency` is the currency for money columns
      that name none: a code (AED, USD, GBP) or a literal symbol. Empty means
      no symbol is invented. */
  export function themed(figure: PlotlyFigure, defaultCurrency = "") {
    const kpi = allIndicators(figure);
    const currency = detectCurrency(figure, symbolFor(defaultCurrency));
  ```

  The rest of `themed`'s body is unchanged.

- [ ] **Step 5: Make `plot.tsx` use it.** In `byd-web/components/plot.tsx`, everything from line 1 to the line before `export function Plot({` becomes:

```tsx
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

```

In `Plot`'s effect, `const { data, layout } = themed(figure);` becomes `const { data, layout } = themed(figure, DEFAULT_CURRENCY);`. Nothing else in `Plot` changes.

- [ ] **Step 6: Point the docs at the new file.**
  - `byd-web/DESIGN.md`: replace `` order is applied as Plotly's `colorway` in `components/plot.tsx`. `` with `` order is applied as Plotly's `colorway` in `lib/plot-theme.ts`. ``; replace `` was re-themed. `plot.tsx` now swaps `` with `` was re-themed. `lib/plot-theme.ts` now swaps ``; replace `` so `components/plot.tsx` re-themes `` with `` so `lib/plot-theme.ts` re-themes ``. The two later mentions of `plot.tsx` (lazy import, print) stay: that code did not move.
  - `AGENTS.md`: replace `Number formatting is a RENDER-layer job in \`byd-web/components/plot.tsx\`` with `Number formatting is a RENDER-layer job in \`byd-web/lib/plot-theme.ts\` (called by \`components/plot.tsx\`, which reads \`NEXT_PUBLIC_DEFAULT_CURRENCY\`)`.

- [ ] **Step 7: Run the checks**

Run: `cd byd-web && npm test && npm run lint && npx tsc --noEmit && npm run build`
Expected: every test passes, including the 6 new ones; lint and tsc print no errors; the build ends with the route table.

- [ ] **Step 8 (controller): Live check.**
  - Reload the report from Step 1. It must match the screenshot: colours, the values above bars, the KPI number and its format, any currency.
  - On the same account, start a dashboard build on one of its sample CSVs and watch the loader: the same pine dots, timing and morphs as before.

- [ ] **Step 9: Commit**

```bash
git add byd-web/lib/plot-theme.ts byd-web/tests/plot-theme.test.mts byd-web/components/plot.tsx byd-web/DESIGN.md AGENTS.md
git commit -m "refactor(web): the chart re-theme moves to lib/plot-theme.ts

themed and its helpers move out of plot.tsx unchanged, so the landing page
can carry a byte-identical copy. The default currency becomes a parameter;
plot.tsx still reads NEXT_PUBLIC_DEFAULT_CURRENCY, since Next inlines it
only where the code names it. Six tests pin the behaviour across the move.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Download the file sources: `backend/scripts/fetch_showcase_data.py`

Downloads Inside Airbnb's two Edinburgh summary files and the Netflix catalogue into `backend/uploads/showcase/`, which git ignores. Saves the listings as Excel without changing them, and writes a manifest of where each file came from. It runs only after Task 1's OK.

**Files:**
- Create: `backend/scripts/fetch_showcase_data.py`
- Test: `backend/tests/test_fetch_showcase_data.py`

**Interfaces:**
- Produces: `backend/uploads/showcase/` holding `listings.xlsx`, `reviews.csv`, `netflix_titles.csv` and `manifest.json`. `manifest.json` is a list of `{"file", "url", "licence", "licence_url", "rows", "bytes", "sha256", "fetched_at", "note"}`, which Task 5 reads.
- Functions: `airbnb_urls(snapshot: str) -> dict[str, str]`, `excel_from_csv(csv_path: Path, xlsx_path: Path) -> int`, `entry(path: Path, url: str, licence: tuple[str, str], rows: int, note: str) -> dict`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_fetch_showcase_data.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_showcase_data import airbnb_urls, entry, excel_from_csv  # noqa: E402

CC_BY = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")


def test_airbnb_urls_point_at_one_snapshot():
    urls = airbnb_urls("2025-09-21")
    assert urls["listings.csv"] == (
        "https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/2025-09-21/visualisations/listings.csv"
    )
    assert urls["reviews.csv"].endswith("/2025-09-21/visualisations/reviews.csv")


def test_a_snapshot_must_be_a_date():
    with pytest.raises(ValueError, match="2025-09-21"):
        airbnb_urls("latest")


def test_the_excel_copy_keeps_every_value(tmp_path):
    source = tmp_path / "listings.csv"
    pd.DataFrame({
        "id": [1234567890123456789, 42],
        "room_type": ["Entire home/apt", "Private room"],
        "price": [120.0, None],
    }).to_csv(source, index=False)
    rows = excel_from_csv(source, tmp_path / "listings.xlsx")
    back = pd.read_excel(tmp_path / "listings.xlsx")
    assert rows == 2
    assert back["id"].tolist() == [1234567890123456789, 42]
    assert back["room_type"].tolist() == ["Entire home/apt", "Private room"]
    assert back["price"].iloc[0] == 120.0 and pd.isna(back["price"].iloc[1])


def test_a_price_stored_as_text_stops_the_conversion(tmp_path):
    source = tmp_path / "listings.csv"
    pd.DataFrame({"price": ["$120.00", "$95.00"]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="price is not numeric"):
        excel_from_csv(source, tmp_path / "listings.xlsx")


def test_a_manifest_entry_records_where_a_file_came_from(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text("listing_id,date\n1,2024-01-01\n", encoding="utf-8")
    item = entry(path, "https://example.org/reviews.csv", CC_BY, 1, "As published.")
    assert item["file"] == "reviews.csv" and item["rows"] == 1 and item["bytes"] == path.stat().st_size
    assert item["licence"] == "CC BY 4.0" and item["url"] == "https://example.org/reviews.csv"
    assert len(item["sha256"]) == 64 and item["fetched_at"].endswith("Z")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_fetch_showcase_data.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'fetch_showcase_data'`.

- [ ] **Step 3: Write `backend/scripts/fetch_showcase_data.py`.** If Task 1 recorded a licence that differs from `AIRBNB_LICENCE` or `NETFLIX_LICENCE`, use the recorded one.

```python
#!/usr/bin/env python3
"""Download the landing page's file sources and record where each came from.

Run once from the repository root, after the owner has agreed to the downloads
(each file's name, source and size). The files go to backend/uploads/showcase/,
which git ignores, so no third-party data is committed:

    listings.xlsx       Inside Airbnb's Edinburgh listings summary, saved as Excel
    reviews.csv         Inside Airbnb's Edinburgh reviews summary, as published
    netflix_titles.csv  the Netflix catalogue, as TidyTuesday mirrors it
    manifest.json       each file's URL, licence, rows, bytes, sha256 and fetch time

The listings are saved as Excel so one dashboard is built from an Excel file and
a CSV, as a user's might be. No value changes on the way.

    backend/.venv/bin/python backend/scripts/fetch_showcase_data.py --airbnb-snapshot 2025-09-21
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AIRBNB_FILE = "https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/{snapshot}/visualisations/{name}"
AIRBNB_LICENCE = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")
NETFLIX_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2021/2021-04-20/netflix_titles.csv"
)
NETFLIX_LICENCE = ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
USER_AGENT = "promptdash-showcase/1.0"
SNAPSHOT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def airbnb_urls(snapshot: str) -> dict[str, str]:
    """The two summary files of one Edinburgh snapshot, by file name."""
    if not SNAPSHOT.match(snapshot):
        raise ValueError(
            f"the snapshot is a date such as 2025-09-21, from insideairbnb.com/get-the-data; got {snapshot!r}"
        )
    return {name: AIRBNB_FILE.format(snapshot=snapshot, name=name) for name in ("listings.csv", "reviews.csv")}


def download(url: str, path: Path) -> None:
    """Fetch through a .part file, so an interrupted download leaves no file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    partial.replace(path)


def excel_from_csv(csv_path: Path, xlsx_path: Path) -> int:
    """Save the listings as Excel, unchanged, and return the row count.

    Stops if `price` is not numeric: cleaning it would be editing the data, and
    the page would have to say so. That is the owner's decision."""
    frame = pd.read_csv(csv_path)
    if "price" in frame.columns and not pd.api.types.is_numeric_dtype(frame["price"]):
        sample = frame["price"].dropna().astype(str).head(3).tolist()
        raise ValueError(f"price is not numeric in {csv_path.name} (for example {sample}); cleaning it would edit the data")
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(xlsx_path, index=False)
    return len(frame)


def entry(path: Path, url: str, licence: tuple[str, str], rows: int, note: str) -> dict:
    """One manifest line: where the file came from, under what licence, and what it holds."""
    return {
        "file": path.name,
        "url": url,
        "licence": licence[0],
        "licence_url": licence[1],
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the landing page's file sources.")
    parser.add_argument("--airbnb-snapshot", required=True, help="the Edinburgh snapshot date on insideairbnb.com")
    parser.add_argument("--out", default="backend/uploads/showcase")
    args = parser.parse_args()
    out = Path(args.out)
    raw = out / "raw"

    airbnb = airbnb_urls(args.airbnb_snapshot)
    for name, url in {**airbnb, "netflix_titles.csv": NETFLIX_URL}.items():
        print(f"downloading {name} from {url}", file=sys.stderr)
        download(url, raw / name)

    snapshot = f"Inside Airbnb, Edinburgh, snapshot {args.airbnb_snapshot}."
    listings_rows = excel_from_csv(raw / "listings.csv", out / "listings.xlsx")
    shutil.copyfile(raw / "reviews.csv", out / "reviews.csv")
    shutil.copyfile(raw / "netflix_titles.csv", out / "netflix_titles.csv")
    manifest = [
        entry(out / "listings.xlsx", airbnb["listings.csv"], AIRBNB_LICENCE, listings_rows,
              f"{snapshot} Saved as Excel from the published CSV."),
        entry(out / "reviews.csv", airbnb["reviews.csv"], AIRBNB_LICENCE, len(pd.read_csv(out / "reviews.csv")),
              f"{snapshot} As published."),
        entry(out / "netflix_titles.csv", NETFLIX_URL, NETFLIX_LICENCE, len(pd.read_csv(out / "netflix_titles.csv")),
              "Netflix Movies and TV Shows by Shivam Bansal on Kaggle, as mirrored by TidyTuesday (2021-04-20)."),
    ]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for item in manifest:
        print(f"{item['file']}: {item['rows']:,} rows, {item['bytes']:,} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_fetch_showcase_data.py`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/fetch_showcase_data.py backend/tests/test_fetch_showcase_data.py
git commit -m "feat(showcase): download the landing page's file sources with their provenance

Inside Airbnb's Edinburgh summaries and the Netflix catalogue go to the
gitignored backend/uploads/showcase/. The listings are saved as Excel
without changing a value (a 19-digit id survives the round trip); a price
stored as text stops the run, since cleaning it would edit the data.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6 (controller): Download.** Only after Task 1's yes, from the repository root, with the snapshot date Task 1 recorded:

Run: `backend/.venv/bin/python backend/scripts/fetch_showcase_data.py --airbnb-snapshot <recorded date>`
Expected: three `downloading` lines, then one line per file with its rows and bytes. `git status --short` shows nothing new, because `backend/uploads/` is ignored. If it stops on `price is not numeric`, ask the owner whether to clean the price (and say so on the page) or to choose another Inside Airbnb file.

---

### Task 5: Build and export one dashboard: `backend/scripts/make_showcase.py`

Builds a dashboard the way a person does: a new, empty report with its sources, then the prompt sent as the dashboard brief. Exports the blocks the app saved, unedited. Runs from the repository root, on the host, against the running stack. It uses the standard library for HTTP, like `smoke_test.py`.

**Files:**
- Create: `backend/scripts/make_showcase.py`
- Modify: `Makefile` (target `showcase`)
- Test: `backend/tests/test_make_showcase.py`

**Interfaces:**
- Consumes: `backend/uploads/showcase/manifest.json` (Task 4). The app's API:
  - `POST /api/v1/auth/register` `{email, full_name, password}` (409 if the account exists), then `POST /api/v1/auth/login` `{email, password}` returns `{access_token}`.
  - `POST /api/v1/data-sources/upload`: multipart field `file`; returns `{id, ...}`.
  - `GET /api/v1/data-sources`; `POST /api/v1/data-sources/db-connection` `{display_name, db_type: "postgresql", db_host, db_port, db_name, db_username, db_password}`; `GET /api/v1/data-sources/{id}/tables` returns table names.
  - `POST /api/v1/dashboard` `{title, data_source_ids}` returns `{id, ...}`. A report with `data_source_ids` builds only from those sources.
  - `POST /api/v1/dashboard/{id}/blocks/dashboard` `{brief}` streams SSE: `status`, `plan` (`total` counts the intro text block), `block` (a saved block), `step`, `skipped` (`{index, label, reason}`), `error`, `done`. The brief is at most 400 characters.
  - `GET /api/v1/dashboard/{id}/blocks` returns the saved blocks.
- Produces: `site/data/dashboards/<name>.json` in the shared dashboard format. Functions: `parse_sse(lines) -> Iterator[tuple[str, dict]]`, `summarize_build(events) -> dict` (`charts_planned`, `skipped`, `missing_kinds`), `export_block(block) -> dict`, `served_model(ps_output) -> dict | None`, `model_record(model) -> dict`, `multipart(field, filename, content) -> tuple[bytes, str]`, `write_dashboard(path, dashboard, limit=MAX_BYTES) -> int`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_make_showcase.py`:

```python
import email
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_showcase import (  # noqa: E402
    SHOWCASES,
    export_block,
    model_record,
    multipart,
    parse_sse,
    served_model,
    summarize_build,
    write_dashboard,
)

STREAM = [
    b"event: status\n", b'data: {"label": "Planning the charts"}\n', b"\n",
    b"event: plan\n", b'data: {"total": 4, "sections": [], "missing_kinds": []}\n', b"\n",
    b"event: block\n", b'data: {"kind": "text", "title": "About this data"}\n', b"\n",
    b"event: skipped\n", b'data: {"index": 2, "label": "Top artists", "reason": "no figure"}\n', b"\n",
    b"event: block\n", b'data: {"kind": "chart", "title": "Popularity by genre"}\n', b"\n",
    b"event: done\n", b'data: {"total": 4}\n', b"\n",
]


def test_each_event_comes_with_its_data():
    events = list(parse_sse(STREAM))
    assert [name for name, _ in events] == ["status", "plan", "block", "skipped", "block", "done"]
    assert events[1][1]["total"] == 4


def test_crlf_lines_read_the_same():
    assert list(parse_sse(["event: done\r\n", 'data: {"total": 1}\r\n', "\r\n"])) == [("done", {"total": 1})]


def test_the_plans_total_counts_the_intro_block():
    assert summarize_build(list(parse_sse(STREAM))) == {
        "charts_planned": 3,
        "skipped": [{"label": "Top artists", "reason": "no figure"}],
        "missing_kinds": [],
    }


def test_a_build_with_no_plan_is_an_error():
    with pytest.raises(RuntimeError, match="no plan"):
        summarize_build([("status", {"label": "Planning"}), ("error", {"message": "the checks failed"})])


def test_the_export_keeps_what_the_app_saved_and_nothing_else():
    saved = {"id": "b1", "kind": "chart", "title": "T", "prompt": "q", "code": "c", "figure": {"data": []},
             "text_body": None, "source_name": "s", "chart_type": "bar", "used_fallback": False,
             "x": 0, "y": 3, "w": 6, "h": 8}
    assert export_block(saved) == {"kind": "chart", "title": "T", "chart_type": "bar", "figure": {"data": []},
                                   "text_body": None, "code": "c", "x": 0, "y": 3, "w": 6, "h": 8}


def test_the_served_model_is_read_from_the_server_command():
    ps = ("/bin/zsh\n"
          "Python -m mlx_lm server --model models/qwen3.5-9b-4bit --adapter-path runs/adapters-mlx-v2 "
          "--host 127.0.0.1 --port 8080\n")
    model = served_model(ps)
    assert model == {"base": "models/qwen3.5-9b-4bit", "adapter": "runs/adapters-mlx-v2"}
    assert model_record(model)["label"] == "lora-v2"
    assert model_record({"base": "models/qwen3.5-9b-4bit", "adapter": "runs/adapters-mlx"})["label"] == "runs/adapters-mlx"
    assert served_model("/bin/zsh\n") is None


def test_an_upload_carries_the_file_unchanged():
    body, content_type = multipart("file", "listings.xlsx", b"\x00\x01binary")
    message = email.message_from_bytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    (part,) = message.get_payload()
    assert part.get_param("name", header="content-disposition") == "file"
    assert part.get_filename() == "listings.xlsx"
    assert part.get_payload(decode=True) == b"\x00\x01binary"


def test_a_dashboard_is_written_compact_and_whole(tmp_path):
    path = tmp_path / "netflix.json"
    size = write_dashboard(path, {"blocks": [{"title": "a"}]})
    assert path.read_text(encoding="utf-8") == '{"blocks":[{"title":"a"}]}'
    assert size == path.stat().st_size
    assert not list(tmp_path.glob("*.tmp"))


def test_a_dashboard_over_the_limit_is_refused_naming_its_largest_block(tmp_path):
    path = tmp_path / "spotify.json"
    blocks = [{"title": "Energy vs danceability", "figure": "x" * 200}, {"title": "small"}]
    with pytest.raises(ValueError, match="Energy vs danceability"):
        write_dashboard(path, {"blocks": blocks}, limit=100)
    assert not path.exists()


def test_every_prompt_fits_the_brief_field():
    assert all(len(config["prompt"]) <= 400 for config in SHOWCASES.values())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_make_showcase.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'make_showcase'`.

- [ ] **Step 3: Write `backend/scripts/make_showcase.py`.** The Spotify `source` line holds Task 1's default; if Task 1 recorded another licence, use that. If Task 1 chose the shop demo, the `shop` entry is the database dashboard.

```python
#!/usr/bin/env python3
"""Build one of the landing page's dashboards with the running app, and export it unedited.

The dashboard is built the way a person builds one: a new, empty report with its
sources, then the prompt sent as the dashboard brief to
POST /api/v1/dashboard/{id}/blocks/dashboard, the endpoint behind the app's
"Build it". The blocks the app saved are exported as it stored them; nothing here
edits a chart. When a dashboard falls short, build it again from a rephrased
--prompt, and count the prompts tried with --tries.

Needs `make up`, `make serve-model`, the files from fetch_showcase_data.py, and
SHOWCASE_PASSWORD in the environment: the password of this script's own local
account (any value; keep it for reruns). Run from the repository root.
`make showcase NAME=...` passes the database login from the postgres container
without printing it.

    SHOWCASE_PASSWORD=... make showcase NAME=airbnb
    SHOWCASE_PASSWORD=... make showcase NAME=airbnb SHOWCASE_PROMPT="..." SHOWCASE_TRIES=2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

MAX_BYTES = 1_500_000
BRIEF_LIMIT = 400  # DashboardBriefRequest.brief in blocks.py
EMAIL = "showcase@example.com"
UPLOADS = Path("backend/uploads/showcase")
LORA_V2 = "runs/adapters-mlx-v2"
BLOCK_KEYS = ("kind", "title", "chart_type", "figure", "text_body", "code", "x", "y", "w", "h")
SPOTIFY_DATA = "https://github.com/rfordatascience/tidytuesday/tree/main/data/2020/2020-01-21"

SHOWCASES: dict[str, dict[str, Any]] = {
    "airbnb": {
        "title": "Airbnb in Edinburgh",
        "prompt": "thinking of renting out my flat in edinburgh on airbnb. which areas charge the most, "
                  "entire place vs private room, and when are guests busiest?",
        "files": ["listings.xlsx", "reviews.csv"],
        "currency": "GBP",  # Inside Airbnb states prices in local currency
    },
    "spotify": {
        "title": "Spotify songs",
        "prompt": "what makes a song popular? compare genres, energy vs danceability, and show me the top artists",
        "database": {"display_name": "Spotify tracks (Postgres)", "db_name": "spotify", "tables": ["tracks"]},
        "source": {"url": SPOTIFY_DATA, "licence": "CC0 1.0 (TidyTuesday)",
                   "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                   "note": "TidyTuesday 2020-01-21, collected from the Spotify Web API with spotifyr."},
        "currency": "",
    },
    "shop": {  # the database dashboard if Task 1 rules Spotify out
        "title": "A demo shop",
        "prompt": "how is my shop doing? revenue by month, which product categories sell best, "
                  "and which customer regions spend the most",
        "database": {"display_name": "Shop demo", "db_name": "shop", "tables": ["orders", "customers", "products"]},
        "source": {"url": "https://github.com/tukka25/BYD/blob/main/backend/scripts/make_relational_demo.py",
                   "licence": "synthetic, made for this project", "licence_url": "",
                   "note": "Seeded by backend/scripts/make_relational_demo.py; the app joins orders to customers and products."},
        "currency": "",
    },
    "netflix": {
        "title": "The Netflix catalogue",
        "prompt": "how has netflix changed over the years? movies vs tv shows, which countries make the most "
                  "content, and the most common ratings",
        "files": ["netflix_titles.csv"],
        "currency": "",
    },
}


# --- pure parts -------------------------------------------------------------

def parse_sse(lines: Iterable[bytes | str]) -> Iterator[tuple[str, dict]]:
    """Server-sent events as (event, data) pairs. The app sends one data line per event."""
    event, data = "message", []
    for raw in lines:
        line = (raw.decode("utf-8") if isinstance(raw, bytes) else raw).rstrip("\r\n")
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


def summarize_build(events: list[tuple[str, dict]]) -> dict:
    """What the build planned and skipped. The plan's total counts the intro text block."""
    plan = next((data for name, data in events if name == "plan"), None)
    if plan is None:
        errors = [data for name, data in events if name == "error"]
        raise RuntimeError(f"the build made no plan: {errors or events[-1:]}")
    return {
        "charts_planned": int(plan["total"]) - 1,
        "skipped": [{"label": data["label"], "reason": data["reason"]} for name, data in events if name == "skipped"],
        "missing_kinds": list(plan.get("missing_kinds") or []),
    }


def export_block(block: dict) -> dict:
    """A saved block as the page needs it, unchanged."""
    return {key: block.get(key) for key in BLOCK_KEYS}


def served_model(ps_output: str) -> dict | None:
    """The running mlx_lm server's --model and --adapter-path, from `ps -axo command`."""
    for line in ps_output.splitlines():
        if re.search(r"mlx_lm[. ]server", line):
            model = re.search(r"--model\s+(\S+)", line)
            adapter = re.search(r"--adapter-path\s+(\S+)", line)
            return {"base": model.group(1) if model else "unknown", "adapter": adapter.group(1) if adapter else "none"}
    return None


def model_record(model: dict) -> dict:
    """The model behind the dashboard. The page says lora-v2 only when the server ran it."""
    return {**model, "label": "lora-v2" if model["adapter"] == LORA_V2 else model["adapter"]}


def multipart(field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    """A multipart/form-data body with one file, and its Content-Type."""
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return head + content + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def write_dashboard(path: Path, dashboard: dict, limit: int = MAX_BYTES) -> int:
    """Write compact JSON through a temporary file, so a failed run leaves no partial file.

    A file over the limit is refused, naming its largest block: change the
    prompt, never the figure."""
    text = json.dumps(dashboard, separators=(",", ":"), ensure_ascii=False)
    size = len(text.encode("utf-8"))
    if size > limit:
        largest = max(dashboard["blocks"], key=lambda block: len(json.dumps(block)))
        raise ValueError(
            f"{path.name} would be {size:,} bytes, over {limit:,}. Its largest block is {largest['title']!r} "
            f"({len(json.dumps(largest)):,} bytes): rephrase the prompt."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return size


# --- talking to the app -------------------------------------------------------

def request(method: str, url: str, *, token: str | None = None, body: dict | None = None,
            raw: bytes | None = None, content_type: str | None = None, timeout: float = 60):
    data = json.dumps(body).encode() if body is not None else raw
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    elif content_type:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=timeout)


def call(method: str, url: str, **kwargs) -> Any:
    try:
        with request(method, url, **kwargs) as response:
            return json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} -> {exc.code}: {exc.read().decode()[:500]}") from None


def login(api: str, password: str) -> str:
    try:
        call("POST", f"{api}/auth/register",
             body={"email": EMAIL, "full_name": "PromptDash showcase", "password": password})
    except RuntimeError as exc:
        if "-> 409" not in str(exc):
            raise
    return call("POST", f"{api}/auth/login", body={"email": EMAIL, "password": password})["access_token"]


def file_sources(api: str, token: str, names: list[str]) -> tuple[list[str], list[dict]]:
    manifest = {item["file"]: item for item in json.loads((UPLOADS / "manifest.json").read_text(encoding="utf-8"))}
    ids, sources = [], []
    for name in names:
        item = manifest[name]
        content = (UPLOADS / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{name} changed since it was fetched; run fetch_showcase_data.py again")
        body, content_type = multipart("file", name, content)
        created = call("POST", f"{api}/data-sources/upload", token=token, raw=body,
                       content_type=content_type, timeout=300)
        ids.append(created["id"])
        sources.append({"name": name, "kind": "file", "rows": item["rows"], "url": item["url"],
                        "licence": item["licence"], "licence_url": item["licence_url"], "note": item["note"]})
    return ids, sources


def count_rows(database: str, table: str, user: str, password: str) -> int:
    import psycopg2
    from psycopg2 import sql

    connection = psycopg2.connect(host="localhost", port=5432, dbname=database, user=user, password=password)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            return int(cursor.fetchone()[0])
    finally:
        connection.close()


def database_source(api: str, token: str, config: dict) -> tuple[list[str], list[dict]]:
    db = config["database"]
    user, password = os.environ["SHOWCASE_DB_USER"], os.environ["SHOWCASE_DB_PASSWORD"]
    existing = [s for s in call("GET", f"{api}/data-sources", token=token) if s["display_name"] == db["display_name"]]
    if existing:
        source_id = existing[0]["id"]
    else:
        # The api container makes this connection, so the host is the compose service name.
        source_id = call("POST", f"{api}/data-sources/db-connection", token=token, body={
            "display_name": db["display_name"], "db_type": "postgresql",
            "db_host": os.environ.get("SHOWCASE_DB_HOST", "postgres"), "db_port": 5432,
            "db_name": db["db_name"], "db_username": user, "db_password": password,
        })["id"]
    tables = call("GET", f"{api}/data-sources/{source_id}/tables", token=token)
    missing = [table for table in db["tables"] if table not in tables]
    if missing:
        raise RuntimeError(f"the {db['db_name']} database has no {missing}; AGENTS.md says how to rebuild it")
    sources = [{"name": f"{db['db_name']}.{table}", "kind": "database",
                "rows": count_rows(db["db_name"], table, user, password), **config["source"]}
               for table in db["tables"]]
    return [source_id], sources


def build(api: str, token: str, report_id: str, prompt: str) -> tuple[list[tuple[str, dict]], float]:
    started = time.monotonic()
    events: list[tuple[str, dict]] = []
    with request("POST", f"{api}/dashboard/{report_id}/blocks/dashboard", token=token,
                 body={"brief": prompt}, timeout=900) as response:
        for name, data in parse_sse(response):
            events.append((name, data))
            print(f"  [{name}] {data.get('label') or data.get('title') or ''}"[:160], file=sys.stderr)
            if name in ("done", "error"):
                break
    return events, round(time.monotonic() - started, 1)


def app_commit() -> str:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "backend/app"], capture_output=True, text=True,
                           check=True)
    return head.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one landing-page dashboard with the running app.")
    parser.add_argument("--name", required=True, choices=sorted(SHOWCASES))
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--prompt", default="", help="a rephrased prompt; the default is the approved one")
    parser.add_argument("--tries", type=int, default=1, help="prompts tried for this dashboard, counting this one")
    parser.add_argument("--out", default="site/data/dashboards")
    args = parser.parse_args()
    config = SHOWCASES[args.name]
    prompt = args.prompt or config["prompt"]
    if len(prompt) > BRIEF_LIMIT:
        print(f"the prompt is {len(prompt)} characters; the brief takes at most {BRIEF_LIMIT}", file=sys.stderr)
        return 2
    password = os.environ.get("SHOWCASE_PASSWORD")
    if not password:
        print("set SHOWCASE_PASSWORD: the password of this script's own local account", file=sys.stderr)
        return 2
    base = args.base.rstrip("/")
    api = f"{base}/api/v1"

    health = call("GET", f"{base}/health")
    model = served_model(subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, check=True).stdout)
    if model is None:
        print("the model server is not running: make serve-model", file=sys.stderr)
        return 2
    print(f"api: {health.get('llm_backend')}; model server: {model['base']} + {model['adapter']}", file=sys.stderr)

    token = login(api, password)
    ids, sources = (database_source(api, token, config) if "database" in config
                    else file_sources(api, token, config["files"]))
    report = call("POST", f"{api}/dashboard", token=token,
                  body={"title": f"Showcase: {config['title']}", "data_source_ids": ids})
    events, seconds = build(api, token, report["id"], prompt)
    if events and events[-1][0] == "error":
        raise RuntimeError(f"the build failed: {events[-1][1]}")
    record = summarize_build(events)
    saved = call("GET", f"{api}/dashboard/{report['id']}/blocks", token=token)
    blocks = sorted((export_block(block) for block in saved), key=lambda block: (block["y"], block["x"]))
    dashboard = {
        "name": args.name,
        "title": config["title"],
        "prompt": prompt,
        "currency": config["currency"],
        "sources": sources,
        "blocks": blocks,
        "build": {
            "charts_planned": record["charts_planned"],
            "charts_drawn": sum(1 for block in blocks if block["kind"] in ("chart", "metric")),
            "skipped": record["skipped"],
            "missing_kinds": record["missing_kinds"],
            "seconds": seconds,
            "prompts_tried": args.tries,
        },
        "model": model_record(model),
        "app_commit": app_commit(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = Path(args.out) / f"{args.name}.json"
    size = write_dashboard(path, dashboard)
    built = dashboard["build"]
    print(f"wrote {path}: {size:,} bytes; {built['charts_drawn']} of {built['charts_planned']} charts drawn "
          f"in {seconds} s; report {report['id']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_make_showcase.py`
Expected: 10 passed.

- [ ] **Step 5: Add the Make target.** In `Makefile`, add `showcase` to the `.PHONY` list, and add this target after `smoke`. Recipe lines start with a tab.

```make
showcase: ## Build one landing-page dashboard with the running app: make showcase NAME=airbnb
	@test -n "$(NAME)" || { echo "usage: make showcase NAME=airbnb|spotify|netflix [SHOWCASE_PROMPT=\"...\" SHOWCASE_TRIES=2]"; exit 2; }
	@SHOWCASE_DB_USER="$$(docker exec promptdash-postgres printenv POSTGRES_USER)" \
	 SHOWCASE_DB_PASSWORD="$$(docker exec promptdash-postgres printenv POSTGRES_PASSWORD)" \
	 $(PY) $(BACKEND)/scripts/make_showcase.py --base $(API_BASE) --name "$(NAME)" \
	   $(if $(SHOWCASE_PROMPT),--prompt "$(SHOWCASE_PROMPT)") --tries $(or $(SHOWCASE_TRIES),1)
```

Run: `make showcase`
Expected: the usage line and exit code 2. (Nothing is built without `NAME`.)

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/make_showcase.py backend/tests/test_make_showcase.py Makefile
git commit -m "feat(showcase): build a landing-page dashboard through the app's API and export it

A new, empty report with its sources, then the prompt sent as the brief,
as the app's Build it does. The saved blocks are exported unedited, with
their sources, the build's events, the served adapter and the commit. A
file over 1.5 MB is refused, naming its largest block: the prompt changes,
the figure does not. make showcase passes the database login from the
postgres container without printing it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Build the three dashboards (controller)

**Files:**
- Create: `site/data/dashboards/airbnb.json`, `site/data/dashboards/netflix.json`, and `site/data/dashboards/spotify.json` (or `shop.json`, if Task 1 chose the shop demo)

- [ ] **Step 1: Check the preconditions.**
  - `pgrep -f evaluate.py` prints nothing. An eval would share the GPU and inflate the recorded seconds.
  - `make doctor` passes.
  - `ps -axo command | grep "mlx_lm server"` shows `--adapter-path runs/adapters-mlx-v2`.
  - `backend/uploads/showcase/manifest.json` exists (Task 4).
- [ ] **Step 2: Make the account's password once and keep it out of sight:**

```bash
SP=<the controller's scratchpad directory>
[ -s "$SP/showcase-password.txt" ] || openssl rand -hex 16 > "$SP/showcase-password.txt"
export SHOWCASE_PASSWORD="$(cat "$SP/showcase-password.txt")"
```

- [ ] **Step 3: Build Airbnb:** `make showcase NAME=airbnb`. It takes 2 to 4 minutes. Expected: one `[status]`, `[plan]` and `[block]` line per event, then `wrote site/data/dashboards/airbnb.json: … bytes; 7 of 7 charts drawn in … s`.
- [ ] **Step 4: Hold it to the quality bar.**
  - Log in to http://localhost:3000 as `showcase@example.com`. This is a local test account made in this session; type its password into the page from the file, never into chat. Open "Showcase: Airbnb in Edinburgh" in View mode.
  - Accept only if every planned chart renders and none is visibly wrong: no stacked raw rows, no empty chart, no title that does not match its chart.
  - Check one number against the source, for example average price by room type, and compare it with the chart's hover values:

```bash
backend/.venv/bin/python -c "import pandas as pd; d = pd.read_excel('backend/uploads/showcase/listings.xlsx'); print(d.groupby('room_type')['price'].mean().round(1))"
```

- [ ] **Step 5: If it falls short, rephrase the prompt as a user would and build again.** Never edit the JSON.

```bash
make showcase NAME=airbnb SHOWCASE_PROMPT="<the rephrased prompt>" SHOWCASE_TRIES=2
```

  Each attempt starts a new, empty report, so no earlier request reaches the planner.
- [ ] **Step 6: Build the database dashboard and Netflix the same way:** `make showcase NAME=spotify` (or `NAME=shop`), then `make showcase NAME=netflix`. Expected snags:
  - **Spotify:** "energy vs danceability" may be drawn as a scatter of all 32,833 songs. `write_dashboard` then refuses the file and names that block. A user's rephrasing: "what makes a song popular? compare genres, how energy and danceability relate to popularity, and show me the top artists".
  - **Netflix:** `country` holds lists such as "United States, India". A chart that counts "United States, India" as one country is visibly wrong: rephrase.
- [ ] **Step 7: Show the owner the three dashboards** (a screenshot of each in View mode), then commit:

```bash
git add site/data/dashboards/
git commit -m "data(site): three showcase dashboards drawn by lora-v2, unedited

<For each dashboard: its charts drawn of planned, the seconds, and the
prompts tried, with the reason for any rephrasing.>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Scaffold `site/` with the four byte-identical copies

A separate Next.js app with byd-web's versions, configs, fonts and tokens. It builds as a static export. A test fails when a `lib/` copy differs from its byd-web original.

**Files:**
- Create: `site/package.json`, `site/next.config.ts`, `site/tsconfig.json`, `site/eslint.config.mjs`, `site/postcss.config.mjs`, `site/.gitignore`
- Create: `site/app/layout.tsx`, `site/app/globals.css`, `site/app/page.tsx` (a stub that Task 9 replaces), `site/app/icon.svg` (a copy of `byd-web/app/icon.svg`)
- Create: `site/lib/dot-shapes.ts`, `site/lib/dot-draw.ts`, `site/lib/plot-theme.ts`, `site/lib/rich-text.ts` (copies made by `npm run sync-lib`)
- Test: `site/tests/copies.test.mts`

**Interfaces:**
- Consumes: Task 2's `byd-web/lib/dot-draw.ts` and Task 3's `byd-web/lib/plot-theme.ts` must be committed first.
- Produces:
  - `npm test`: Node's runner over `site/tests/*.test.mts`.
  - `npm run sync-lib`: copies the four files from byd-web.
  - `npm run dev`: port 3100, so it never collides with the app on 3000.
  - The `@/` alias maps to `site/`.
  - CSS tokens as Tailwind colours (`bg-canvas`, `bg-surface`, `bg-sunken`, `bg-inverse`, `text-ink`, `text-body`, `text-muted`, `text-on-dark`, `text-pine`, `bg-pine`, `bg-pine-wash`, `ring-hairline`), `font-display`, `font-mono`, and the `.rich-text` and `.tabular` classes.

- [ ] **Step 1: Write the failing test** `site/tests/copies.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/* The hero animation, the chart re-theme and the note sanitiser are the app's
   own code, not lookalikes: each file here must be byte-identical to its
   byd-web original. Change the original, then run `npm run sync-lib`. */
const COPIES = ["dot-shapes.ts", "dot-draw.ts", "plot-theme.ts", "rich-text.ts"];

for (const name of COPIES) {
  test(`lib/${name} is byte-identical to byd-web/lib/${name}`, () => {
    const copy = readFileSync(new URL(`../lib/${name}`, import.meta.url));
    const original = readFileSync(new URL(`../../byd-web/lib/${name}`, import.meta.url));
    assert.ok(copy.equals(original), `site/lib/${name} differs from byd-web/lib/${name}: run npm run sync-lib`);
  });
}
```

- [ ] **Step 2: Create the package and its configs.**

`site/package.json`:

```json
{
  "name": "promptdash-site",
  "version": "0.1.0",
  "private": true,
  "engines": {
    "node": "24.x"
  },
  "scripts": {
    "dev": "next dev --port 3100",
    "build": "next build",
    "lint": "eslint",
    "test": "node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mts",
    "sync-lib": "cp ../byd-web/lib/dot-shapes.ts ../byd-web/lib/dot-draw.ts ../byd-web/lib/plot-theme.ts ../byd-web/lib/rich-text.ts lib/"
  },
  "dependencies": {
    "next": "16.1.6",
    "plotly.js-dist-min": "4.3.0",
    "react": "19.2.3",
    "react-dom": "19.2.3"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.1.6",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

`site/next.config.ts`:

```ts
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // A static site: everything the page shows is in the build (site/data/).
  output: "export",
  // site/ is one project inside a larger repository, like byd-web. Pin the
  // workspace root here, or Turbopack walks up to the git root and resolves
  // dependencies from a node_modules that does not exist there.
  turbopack: {
    root: projectDir,
  },
  outputFileTracingRoot: projectDir,
};

export default nextConfig;
```

`site/tsconfig.json`, `site/eslint.config.mjs` and `site/postcss.config.mjs`: copy byd-web's unchanged.

```bash
cp byd-web/tsconfig.json byd-web/eslint.config.mjs byd-web/postcss.config.mjs site/
```

`site/.gitignore`:

```gitignore
/node_modules
/.next/
/out/
.DS_Store
.env*
.vercel
*.tsbuildinfo
next-env.d.ts
```

- [ ] **Step 3: Install, copy the four files, and run the test**

Run: `cd site && npm install && mkdir -p lib && npm run sync-lib && npm test`
Expected: 4 tests pass. Then break one copy to see the test catch it, and restore it:

Run: `echo "// drift" >> lib/rich-text.ts && npm test; npm run sync-lib && npm test`
Expected: the first run fails with `site/lib/rich-text.ts differs from byd-web/lib/rich-text.ts`; after `sync-lib` all 4 pass.

- [ ] **Step 4: Fonts and layout.** `site/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { JetBrains_Mono, Outfit, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

// The app's three faces under the app's variable names: the chart re-theme
// (lib/plot-theme.ts) asks for --font-outfit and --font-jakarta. next/font
// fetches them at build time and serves them from this site's own origin.
const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  display: "swap",
});

const jakarta = Plus_Jakarta_Sans({
  variable: "--font-jakarta",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "PromptDash · dashboards from plain words",
  description:
    "Ask for a dashboard in plain words. A 9B model fine-tuned to write Plotly draws every chart, on your own machine.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${outfit.variable} ${jakarta.variable} ${jetbrainsMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Styles.** Build `site/app/globals.css` from byd-web's tokens, base rules and note styles, then the page's own rules. First check the boundaries:

Run: `sed -n '24p;212p;225p;316p' byd-web/app/globals.css`
Expected: `:root {`, an empty line, `/* --- note blocks ---…`, an empty line. If they differ, find the same blocks by those first lines: from `:root {` to the end of the `a { … }` rule, and from `/* --- note blocks` to the end of the `.rich-text[data-empty]::before { … }` rule.

```bash
cd site
{
  printf '@import "tailwindcss";\n\n'
  printf '/* Tokens, base rules and note styles copied from byd-web/app/globals.css\n   (lines 24-212 and 225-316), so the page and the app share one visual\n   language. Copy them again if those blocks change. */\n\n'
  sed -n '24,212p' ../byd-web/app/globals.css
  sed -n '225,316p' ../byd-web/app/globals.css
  cat <<'EOF'
/* --- the landing page ------------------------------------------------------ */

html {
  scroll-padding-top: 24px;
}

@media (prefers-reduced-motion: no-preference) {
  html {
    scroll-behavior: smooth;
  }
}

/* As in the app: Plotly has no line-cap option for scatter traces. */
.js-plotly-plot .scatterlayer .js-line,
.js-plotly-plot .scatterlayer .lines path {
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* As in the app: reduced motion collapses every animation and transition. */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
EOF
} > app/globals.css
cp ../byd-web/app/icon.svg app/icon.svg
```

- [ ] **Step 6: A stub page, so the app builds.** `site/app/page.tsx` (Task 9 replaces it):

```tsx
export default function Home() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
      <h1 className="font-display text-5xl font-bold">PromptDash</h1>
    </main>
  );
}
```

- [ ] **Step 7: Lint and build**

Run: `cd site && npm run lint && npm run build && ls out/index.html`
Expected: no lint errors; the build lists `/` as static (○); `out/index.html` exists.

- [ ] **Step 8: Commit**

```bash
git add site/package.json site/package-lock.json site/next.config.ts site/tsconfig.json site/eslint.config.mjs \
  site/postcss.config.mjs site/.gitignore site/app site/lib site/tests
git commit -m "feat(site): scaffold the landing page with byte-identical copies of byd-web's lib

A static Next.js export with byd-web's versions, fonts and tokens. The dot
animation, the chart re-theme and the note sanitiser are copied, not
rewritten; a test fails when a copy drifts from its original.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
