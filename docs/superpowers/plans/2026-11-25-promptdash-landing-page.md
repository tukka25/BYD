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
