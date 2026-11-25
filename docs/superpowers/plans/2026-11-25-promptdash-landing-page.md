# PromptDash Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static landing page for PromptDash in `site/`, deployed by Vercel, that tells how the chartist was fine-tuned, quotes only checked numbers, and shows three dashboards the app drew, each with the prompt that drew it.

**Architecture:** Two byd-web components give up their pure parts to `byd-web/lib/` (the dot animation and the chart re-theme), so the site can carry byte-identical copies. `backend/scripts/make_showcase.py` builds each dashboard through the running app's HTTP API, the way a person does, and exports the saved blocks unedited to `site/data/dashboards/`. `site/` is a separate Next.js 16 app with `output: "export"`. Every number it shows is in `site/data/stats.json`, and `npm test` checks each one against the file that recorded it.

**Tech Stack:** Next.js 16.1.6 (App Router, static export, Turbopack), React 19.2.3, Tailwind CSS 4, TypeScript 5, plotly.js-dist-min 4.3.0, Node 24's built-in test runner (it strips TypeScript itself); Python 3.13 standard library (`urllib`) for the scripts, pandas + openpyxl for the Excel file, psycopg2 for one row count; pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-promptdash-landing-page-design.md`

## Departures from the spec

Decided while planning. Reviewers should not flag these; the owner can overrule any of them.

- **One dashboard at a time, behind tabs** (Task 10). The spec does not say how the three sit. Tabs keep the page short and load one dashboard's charts at a time. Stacking all three is a small change in `dashboard-tabs.tsx`.
- **A "Show the code that drew this" button on each chart** (Task 10), as the app's View mode has. It shows that every chart is the model's own code, and the dashboard files carry `code` for it.
- **No "Build it" button in the prompt box** (Task 10). The box is read-only and says what the build drew. A button that does nothing would invite clicks.
- **On a dashboard, the planner titles the charts** (Task 11). The spec's diagram ended with the narrator, which titles single charts from the ask bar. The page says so in one line.
- **The data story counts the 254 docs rows** (Task 11). The scraped examples were not set aside: 254 of lora-v1's 1,929 rows are docs examples rewritten to the app's contract.
- **A fallback prompt for the shop demo** (Task 5), used only if Task 1 rules Spotify out, and approved by the owner in Task 1 if so.

## Global Constraints

- Work in the main checkout, `/Users/atukka/Desktop/BYD`, on branch `feat/landing-page`, not in a worktree. The showcase needs the running stack (containers `promptdash-api`, `promptdash-postgres`, `promptdash-web`), the model server (`make serve-model`, 127.0.0.1:8080, lora-v2) and gitignored files (`backend/uploads/`, `chartist-finetune/models/`, the venvs).
- byd-web on :3000 hot-reloads this checkout's `byd-web/app`, `lib` and `components`. Every byd-web commit leaves the app working.
- A number with no recorded source does not go on the page.
- Charts are never edited. When a dashboard falls short, the prompt changes the way a user would rephrase it, and the dashboard is built again. No hardcoded charts: every chart on the page is the app's unedited output.
- Downloads need the owner's OK first, with each file's name, source and size. Task 1 asks once for all of them: the data files (Task 4) and `site/`'s npm packages (Task 7).
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
- [ ] **Step 5: Ask the owner in one message,** and wait for a clear yes:
  - each file's name, source URL and size, and each licence with its link;
  - the Spotify decision (if it is the shop demo, the shop prompt in Task 5 too);
  - Task 7's `npm install` in `site/`: the packages byd-web already uses (next 16.1.6, react 19.2.3, plotly.js-dist-min 4.3.0, Tailwind 4, ESLint 9, TypeScript 5), from the npm registry.

  Anything the owner changes overrides the defaults below.
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

Run: `cd byd-web && npm test && npm run lint && npx tsc --noEmit && npm run build`
Expected: every test passes, including the 3 new ones; lint and tsc print no errors; the build ends with the route table. The build matters here: `lib/dot-draw.ts` is byd-web's first explicit `.ts` import, and only Turbopack proves it resolves. The app on :3000 hot-reloads this commit.

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
- Functions: `airbnb_urls(snapshot: str) -> dict[str, str]`, `excel_from_csv(csv_path: Path, xlsx_path: Path) -> tuple[int, list[str]]` (rows, and the columns written as text), `entry(path: Path, url: str, licence: tuple[str, str], rows: int, note: str) -> dict`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_fetch_showcase_data.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

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
    rows, as_text = excel_from_csv(source, tmp_path / "listings.xlsx")
    back = pd.read_excel(tmp_path / "listings.xlsx")
    assert rows == 2
    # Excel stores numbers as doubles, exact only up to 2**53, so a 19-digit id
    # is stored as a text cell, and pandas reads every digit back.
    assert as_text == ["id"]
    sheet = load_workbook(tmp_path / "listings.xlsx").active
    assert [sheet["A2"].value, sheet["A3"].value] == ["1234567890123456789", "42"]
    assert back["id"].astype(str).tolist() == ["1234567890123456789", "42"]
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


def excel_from_csv(csv_path: Path, xlsx_path: Path) -> tuple[int, list[str]]:
    """Save the listings as Excel, keeping every value. Returns the row count and
    the columns written as text.

    Excel stores numbers as doubles, which hold integers exactly only up to
    2**53: a 19-digit listing id would come back with other digits. Such a column
    is written as text, digit for digit, and the manifest says so.

    Stops if `price` is not numeric: cleaning it would be editing the data, and
    the page would have to say so. That is the owner's decision."""
    frame = pd.read_csv(csv_path)
    if "price" in frame.columns and not pd.api.types.is_numeric_dtype(frame["price"]):
        sample = frame["price"].dropna().astype(str).head(3).tolist()
        raise ValueError(f"price is not numeric in {csv_path.name} (for example {sample}); cleaning it would edit the data")
    as_text = [
        name for name in frame.columns
        if pd.api.types.is_integer_dtype(frame[name]) and frame[name].abs().max() > 2**53
    ]
    for name in as_text:
        frame[name] = frame[name].astype(str)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(xlsx_path, index=False)
    return len(frame), as_text


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
    listings_rows, as_text = excel_from_csv(raw / "listings.csv", out / "listings.xlsx")
    kept = f"; {', '.join(as_text)} stored as text to keep every digit" if as_text else ""
    shutil.copyfile(raw / "reviews.csv", out / "reviews.csv")
    shutil.copyfile(raw / "netflix_titles.csv", out / "netflix_titles.csv")
    manifest = [
        entry(out / "listings.xlsx", airbnb["listings.csv"], AIRBNB_LICENCE, listings_rows,
              f"{snapshot} Saved as Excel from the published CSV{kept}."),
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
without changing a value: an integer too long for an Excel number (the
19-digit listing ids) is written as text, digit for digit, and the manifest
says so. A price stored as text stops the run, since cleaning it would edit
the data.

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
        "database": {"display_name": "Shop demo", "db_name": "shop", "tables": ["orders", "customers", "products", "visits"]},
        "source": {"url": "https://github.com/tukka25/BYD/blob/main/backend/scripts/make_relational_demo.py",
                   "licence": "synthetic, made for this project", "licence_url": "",
                   "note": "Seeded by backend/scripts/make_relational_demo.py: four tables, joined by their declared keys."},
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
### Task 6b: The re-theme owns the currency (added 2026-11-25, the owner's choice)

Found while showing the three dashboards: the model wrote a `$` prefix into three KPI cards (Airbnb's median nightly price, in pounds; the shop's total revenue and average order, whose data names no currency). Today's re-theme keeps a prefix the model chose, and worse, `figureWords` reads the number's own prefix and suffix, so the model's `$` convinces the app the data is in dollars. The app's rule (AGENTS.md) is "never invent a currency for an unlabelled column": it must hold for the model's marks too. No chart is edited or rebuilt: this is the render layer, in the app and (through Task 7's copy) the landing page.

**Files:**
- Modify: `byd-web/lib/plot-theme.ts`
- Modify: `byd-web/tests/plot-theme.test.mts` (add tests)
- Modify: `byd-web/DESIGN.md` (one bullet), `AGENTS.md` (one sentence)

**Interfaces:** `themed(figure, defaultCurrency = "")` keeps its signature. Behaviour change only:
- The data's currency is read from the figure's words without the model's own marks: `figureWords` no longer includes an indicator's `number.prefix` and `number.suffix`.
- A currency mark the model wrote (an indicator's `number.prefix` or `number.suffix`, d3's `$` flag in `number.valueformat`, an axis `tickprefix`) gives way to the data's currency, or goes when the data names none. Any other prefix or suffix (such as `~` or `+`) is kept.

- [ ] **Step 1: Write the failing tests.** Append to `byd-web/tests/plot-theme.test.mts` (it already has `at`, `bars` and the imports):

```ts
const priceKpi = (number: Record<string, unknown>, title = "Overall Median Nightly Price") => ({
  data: [{ type: "indicator", mode: "number", value: 215, number }],
  layout: { title: { text: title } },
});

test("a currency the model wrote on a KPI gives way to the data's currency", () => {
  assert.equal(at(themed(priceKpi({ prefix: "$", valueformat: ",.2f" }), "GBP").data[0], "number", "prefix"), "£");
});

test("a currency the model wrote is dropped when the data names none", () => {
  const { data } = themed(priceKpi({ prefix: "$", valueformat: ",.2f" }));
  assert.equal(at(data[0], "number", "prefix"), undefined);
  assert.equal(at(data[0], "number", "valueformat"), ",.2f");
});

test("a currency the data names is kept, whatever the model wrote", () => {
  assert.equal(at(themed(priceKpi({ prefix: "$" }, "Total MRR (USD)")).data[0], "number", "prefix"), "$");
  assert.equal(at(themed(priceKpi({ prefix: "€" }, "Total MRR (USD)")).data[0], "number", "prefix"), "$");
});

test("d3's $ flag in a KPI format is a currency mark too", () => {
  const plain = themed(priceKpi({ valueformat: "$,.2f" }));
  assert.equal(at(plain.data[0], "number", "valueformat"), ",.2f");
  assert.equal(at(plain.data[0], "number", "prefix"), undefined);
  assert.equal(at(themed(priceKpi({ valueformat: "$,.2f" }), "EUR").data[0], "number", "prefix"), "€");
});

test("a currency code the model wrote as a suffix goes the same way", () => {
  const { data } = themed(priceKpi({ suffix: " USD" }), "GBP");
  assert.equal(at(data[0], "number", "suffix"), undefined);
  assert.equal(at(data[0], "number", "prefix"), "£");
});

test("a prefix that is not a currency stays", () => {
  assert.equal(at(themed(priceKpi({ prefix: "~" })).data[0], "number", "prefix"), "~");
});

test("a currency tick prefix the model put on an axis gives way to the data's", () => {
  const figure = { data: [bars(3)], layout: { yaxis: { title: { text: "Revenue" }, tickprefix: "$" } } };
  assert.equal(at(themed(figure).layout, "yaxis", "tickprefix"), undefined);
  assert.equal(at(themed(figure, "GBP").layout, "yaxis", "tickprefix"), "£");
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd byd-web && npm test`
Expected: the new tests fail (for example the first gets `"$"` where it expects `"£"`); the earlier 22 pass.

- [ ] **Step 3: Implement in `byd-web/lib/plot-theme.ts`.**

  1. In `figureWords`, delete these two lines (they read the model's own marks as if they were the data's words):

  ```ts
      const number = raw.number as Record<string, unknown> | undefined;
      if (number) parts.push(String(number.prefix ?? ""), String(number.suffix ?? ""));
  ```

  2. After the `CURRENCIES` list, add:

  ```ts
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
  ```

  3. In `themed`, right after the `const layout: Record<string, unknown> = { ... };` statement and before `const data = (figure.data ?? []).map(`, add:

  ```ts
    // An axis currency the model wrote gives way to the data's (see CURRENCY_MARK).
    for (const axis of ["xaxis", "yaxis"] as const) {
      const value = layout[axis] as Record<string, unknown>;
      if (isCurrencyMark(value.tickprefix)) value.tickprefix = currency || undefined;
    }
  ```

  4. In the indicator branch, replace

  ```ts
      const chosen = String(number.valueformat ?? "");
      if (!chosen || !D3_FORMAT.test(chosen) || !READABLE_FORMAT.test(chosen)) {
        number.valueformat = numberFormat(trace.value);
      }
      if (currency && !number.prefix && !number.suffix) number.prefix = currency;
  ```

  with

  ```ts
      // The model's own currency marks give way to the data's (see CURRENCY_MARK).
      if (isCurrencyMark(number.prefix)) delete number.prefix;
      if (isCurrencyMark(number.suffix)) delete number.suffix;
      // d3's "$" flag prints a dollar sign: a currency mark like the others.
      const chosen = String(number.valueformat ?? "").replace("$", "");
      number.valueformat =
        chosen && D3_FORMAT.test(chosen) && READABLE_FORMAT.test(chosen) ? chosen : numberFormat(trace.value);
      if (currency && !number.prefix && !number.suffix) number.prefix = currency;
  ```

  Keep the long comment block above `const chosen` that explains which formats are kept; it still holds.

- [ ] **Step 4: Run the checks**

Run: `cd byd-web && npm test && npm run lint && npx tsc --noEmit && npm run build`
Expected: all tests pass (22 earlier + 7 new = 29), lint and tsc clean, the build ends with the route table.

- [ ] **Step 5: Docs.**
  - `byd-web/DESIGN.md`, in the "What we override" list of section 8, after the bullet `- hover label: white, hairline border, ink text`, add: `- a currency mark the model wrote itself (a KPI prefix or suffix, d3's \`$\` flag, an axis tick prefix) gives way to the data's currency, and goes when the data names none`
  - `AGENTS.md`, at the end of the bullet that starts `Number formatting is a RENDER-layer job`, add: ` A currency mark the model writes itself (a KPI prefix or suffix, d3's \`$\` flag, an axis tick prefix) gives way to the data's currency, or goes when the data names none: on 2026-11-25 it wrote \`$\` for Edinburgh prices in pounds and for a shop whose data names no currency.`

- [ ] **Step 6: Commit**

```bash
git add byd-web/lib/plot-theme.ts byd-web/tests/plot-theme.test.mts byd-web/DESIGN.md AGENTS.md
git commit -m "fix(web): a currency the model writes gives way to the data's, or goes

The model wrote \$ on three KPI cards: Edinburgh prices in pounds, and a
shop whose data names no currency. The re-theme kept it, and read it back
as the data's own currency. Now only the data's words decide the currency;
a mark the model wrote (KPI prefix or suffix, d3's \$ flag, an axis tick
prefix) takes the data's currency or goes. Other prefixes stay.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7 (controller): Live check.** The Bounce-rate report's fingerprint (ledger) stays the same for charts with no currency mark; the showcase Airbnb KPI shows the machine's default currency instead of `$`.

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

- [ ] **Step 3: Install, copy the four files, and run the test.** The install is covered by the owner's OK in Task 1.

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
### Task 8: Every number, loss point and milestone, checked against its source

`stats.json` holds every number on the page as the raw value its source recorded. `loss.json` holds the two validation-loss curves, and `journey.json` the dated milestones. Three tests read each value back from the file or commit that recorded it. Every quote below was checked against its file when this plan was written.

**Files:**
- Create: `site/lib/stats.ts`
- Create: `site/data/stats.json`, `site/data/loss.json`, `site/data/journey.json`
- Test: `site/tests/stats.test.mts`, `site/tests/loss.test.mts`, `site/tests/journey.test.mts`

**Interfaces:**
- Produces:
  - `type StatFormat = { kind: "percent" | "usd" | "number"; decimals: number } | { kind: "duration" }`
  - `type StatSource = { kind: "json"; file: string; path: (string | number)[] } | { kind: "quote"; file: string; quote: string } | { kind: "sum"; of: string[] }`
  - `type Stat = { id: string; value: number; format: StatFormat; label: string; source: StatSource }`
  - `formatStat(stat: Pick<Stat, "value" | "format">, decimals?: number): string`
  - `findStat(stats: readonly Stat[], id: string): Stat`, which throws on an unknown id, so a missing number fails the build.
  - `loss.json`: `{ v1: { label, points: number[], source: { file, quote } }, v2: { label, steps: number[], points: number[], source: { file } } }`.
  - `journey.json`: `Array<{ date, commit, subject, title, text }>`.
  - The stat ids used by Tasks 9 and 11 are the `id`s in `stats.json` below.

- [ ] **Step 1: Write the failing tests.**

`site/tests/stats.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { findStat, formatStat, type Stat } from "../lib/stats.ts";

const ROOT = new URL("../../", import.meta.url);
const stats: Stat[] = JSON.parse(readFileSync(new URL("../data/stats.json", import.meta.url), "utf8"));
const read = (file: string) => readFileSync(new URL(file, ROOT), "utf8");
const squash = (text: string) => text.replace(/\s+/g, " ");

function at(value: unknown, path: (string | number)[]): unknown {
  return path.reduce<unknown>((node, key) => (node as Record<string | number, unknown> | undefined)?.[key], value);
}

test("percent, money, counts and durations format as the page shows them", () => {
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }), "94.3%");
  assert.equal(formatStat({ value: 0.9433, format: { kind: "percent", decimals: 1 } }, 0), "94%");
  assert.equal(formatStat({ value: 34.85, format: { kind: "usd", decimals: 0 } }), "$35");
  assert.equal(formatStat({ value: 5.4708, format: { kind: "usd", decimals: 4 } }, 2), "$5.47");
  assert.equal(formatStat({ value: 1832, format: { kind: "number", decimals: 0 } }), "1,832");
  assert.equal(formatStat({ value: 8668, format: { kind: "duration" } }), "2 h 24 m");
});

test("ids are unique and every entry says what it measures", () => {
  assert.equal(new Set(stats.map((stat) => stat.id)).size, stats.length);
  for (const stat of stats) assert.ok(stat.label.length > 10, `${stat.id} needs a label`);
});

test("an unknown id fails loudly", () => {
  assert.throws(() => findStat(stats, "no_such_stat"), /no stat with id no_such_stat/);
});

for (const stat of stats) {
  test(`${stat.id} matches its source`, () => {
    const source = stat.source;
    if (source.kind === "json") {
      assert.equal(at(JSON.parse(read(source.file)), source.path), stat.value);
    } else if (source.kind === "quote") {
      assert.ok(squash(read(source.file)).includes(squash(source.quote)), `${source.file} lacks: ${source.quote}`);
      assert.ok(source.quote.includes(formatStat(stat)), `the quote does not contain ${formatStat(stat)}`);
    } else {
      const total = source.of.reduce((sum, id) => sum + findStat(stats, id).value, 0);
      assert.ok(Math.abs(total - stat.value) < 1e-9, `${stat.id} is ${stat.value}; its parts add up to ${total}`);
    }
  });
}
```

`site/tests/loss.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ROOT = new URL("../../", import.meta.url);
const loss = JSON.parse(readFileSync(new URL("../data/loss.json", import.meta.url), "utf8"));
const squash = (text: string) => text.replace(/\s+/g, " ");

test("lora-v1's validation losses are the ones its run recorded", () => {
  const readme = squash(readFileSync(new URL(loss.v1.source.file, ROOT), "utf8"));
  assert.ok(readme.includes(loss.v1.source.quote));
  assert.deepEqual(loss.v1.points, (loss.v1.source.quote.match(/\d+\.\d+/g) ?? []).map(Number));
});

test("lora-v2's validation losses are the trainer's own log, to four places", () => {
  const state = JSON.parse(readFileSync(new URL(loss.v2.source.file, ROOT), "utf8"));
  const evals = state.log_history.filter((entry: { eval_loss?: number }) => entry.eval_loss !== undefined);
  assert.deepEqual(loss.v2.steps, evals.map((entry: { step: number }) => entry.step));
  assert.deepEqual(
    loss.v2.points,
    evals.map((entry: { eval_loss: number }) => Math.round(entry.eval_loss * 1e4) / 1e4),
  );
});
```

`site/tests/journey.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

type Milestone = { date: string; commit: string; subject: string; title: string; text: string };
const journey: Milestone[] = JSON.parse(readFileSync(new URL("../data/journey.json", import.meta.url), "utf8"));

/* If part 2 rewrites the history, these hashes change. Find each milestone's
   new hash by its subject: git log --format='%h %ad %s' --date=short */
for (const milestone of journey) {
  test(`${milestone.date} "${milestone.title}" is commit ${milestone.commit}`, () => {
    const shown = execFileSync("git", ["show", "-s", "--format=%ad%x09%s", "--date=short", milestone.commit], {
      encoding: "utf8",
    }).trim();
    assert.equal(shown, `${milestone.date}\t${milestone.subject}`);
  });
}

test("the milestones run in date order", () => {
  const dates = journey.map((milestone) => milestone.date);
  assert.deepEqual(dates, [...dates].sort());
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd site && npm test`
Expected: FAIL: `Cannot find module '.../lib/stats.ts'`, and `ENOENT` for the three data files.

- [ ] **Step 3: Write `site/lib/stats.ts`:**

```ts
/* Every number on the page, formatted from the raw value its source recorded.
   The entries live in data/stats.json, and tests/stats.test.mts reads each one
   back from its source. Import-free, so Node's test runner can load it. */

export type StatFormat = { kind: "percent" | "usd" | "number"; decimals: number } | { kind: "duration" };

export type StatSource =
  | { kind: "json"; file: string; path: (string | number)[] }
  | { kind: "quote"; file: string; quote: string }
  | { kind: "sum"; of: string[] };

export type Stat = { id: string; value: number; format: StatFormat; label: string; source: StatSource };

function grouped(value: number, decimals: number): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** The value as the page shows it. `decimals` shows fewer places: 94% from 0.9433. */
export function formatStat(stat: Pick<Stat, "value" | "format">, decimals?: number): string {
  const { value, format } = stat;
  if (format.kind === "duration") {
    const hours = Math.floor(value / 3600);
    const minutes = Math.round((value - hours * 3600) / 60);
    return `${hours} h ${minutes} m`;
  }
  const places = decimals ?? format.decimals;
  if (format.kind === "percent") return `${(value * 100).toFixed(places)}%`;
  if (format.kind === "usd") return `$${grouped(value, places)}`;
  return grouped(value, places);
}

/** The entry with this id. Throws, so a missing number fails the build instead of printing nothing. */
export function findStat(stats: readonly Stat[], id: string): Stat {
  const found = stats.find((stat) => stat.id === id);
  if (!found) throw new Error(`no stat with id ${id} in data/stats.json`);
  return found;
}
```

- [ ] **Step 4: Write `site/data/stats.json`:**

```json
[
  {"id": "base_render_mac", "value": 0.6867, "format": {"kind": "percent", "decimals": 1}, "label": "Base Qwen3.5-9B, thinking off: chart scripts that run, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_base_nothink.json", "path": ["base-nothink", "render_rate"]}},
  {"id": "base_shape_mac", "value": 0.4633, "format": {"kind": "percent", "decimals": 1}, "label": "Base Qwen3.5-9B, thinking off: the right kind of chart, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_base_nothink.json", "path": ["base-nothink", "right_shape_rate"]}},
  {"id": "v1_render_mac", "value": 0.8933, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: chart scripts that run, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_v1.json", "path": ["lora-v1", "render_rate"]}},
  {"id": "v1_shape_mac", "value": 0.7633, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: the right kind of chart, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_v1.json", "path": ["lora-v1", "right_shape_rate"]}},
  {"id": "v2_render_mac", "value": 0.9433, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: chart scripts that run, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_v2.json", "path": ["lora-v2", "render_rate"]}},
  {"id": "v2_shape_mac", "value": 0.8233, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: the right kind of chart, frozen 300, 4-bit on a Mac", "source": {"kind": "json", "file": "chartist-finetune/data/eval_report_local_v2.json", "path": ["lora-v2", "right_shape_rate"]}},
  {"id": "v1_v2_p", "value": 0.02, "format": {"kind": "number", "decimals": 3}, "label": "lora-v1 against lora-v2 on the Mac, scripts that run: exact McNemar p", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "exact McNemar p = 0.020"}},
  {"id": "base_render_pod", "value": 0.0767, "format": {"kind": "percent", "decimals": 1}, "label": "Base Qwen3.5-9B, thinking on: chart scripts that run, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report.json", "path": ["base", "render_rate"]}},
  {"id": "base_shape_pod", "value": 0.0467, "format": {"kind": "percent", "decimals": 1}, "label": "Base Qwen3.5-9B, thinking on: the right kind of chart, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report.json", "path": ["base", "right_shape_rate"]}},
  {"id": "v1_render_pod", "value": 0.9133, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: chart scripts that run, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report.json", "path": ["lora-v1", "render_rate"]}},
  {"id": "v1_shape_pod", "value": 0.81, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: the right kind of chart, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report.json", "path": ["lora-v1", "right_shape_rate"]}},
  {"id": "v2_render_pod", "value": 0.9733, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: chart scripts that run, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report_v2.json", "path": ["lora-v2", "render_rate"]}},
  {"id": "v2_shape_pod", "value": 0.87, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: the right kind of chart, frozen 300, full precision", "source": {"kind": "json", "file": "chartist-finetune/cloud/eval_report_v2.json", "path": ["lora-v2", "right_shape_rate"]}},
  {"id": "plan_requests", "value": 120, "format": {"kind": "number", "decimals": 0}, "label": "Frozen dashboard requests in the planning evaluation", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v2.json", "path": ["summary", "rows"]}},
  {"id": "plan_drawn_per_dashboard", "value": 3, "format": {"kind": "number", "decimals": 0}, "label": "Charts drawn per dashboard in the planning evaluation, the first ones planned", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "It draws only the FIRST 3 plans of each dashboard"}},
  {"id": "plan_retry_v1", "value": 0.5416666666666666, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: dashboards whose plan needed a retry", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v1.json", "path": ["summary", "rows_needing_retries"]}},
  {"id": "plan_retry_v2", "value": 0.125, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: dashboards whose plan needed a retry", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v2.json", "path": ["summary", "rows_needing_retries"]}},
  {"id": "plan_render_v1", "value": 0.8636363636363636, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: planned charts that render", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v1.json", "path": ["summary", "render_rate"]}},
  {"id": "plan_render_v2", "value": 0.988795518207283, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: planned charts that render", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v2.json", "path": ["summary", "render_rate"]}},
  {"id": "plan_kind_v1", "value": 0.8494318181818182, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v1: planned charts drawn as the planned kind", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v1.json", "path": ["summary", "right_chart_rate"]}},
  {"id": "plan_kind_v2", "value": 0.988795518207283, "format": {"kind": "percent", "decimals": 1}, "label": "lora-v2: planned charts drawn as the planned kind", "source": {"kind": "json", "file": "chartist-finetune/data/v2/planning_eval_lora-v2.json", "path": ["summary", "right_chart_rate"]}},
  {"id": "scraped_rows", "value": 970, "format": {"kind": "number", "decimals": 0}, "label": "Rows scraped from plotly.com/python", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "was 970 rows scraped from plotly.com/python"}},
  {"id": "scraped_json_print", "value": 0, "format": {"kind": "percent", "decimals": 0}, "label": "Scraped rows that end with print(fig.to_json())", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| ends with `print(fig.to_json())` | 0% |"}},
  {"id": "scraped_show", "value": 0.961, "format": {"kind": "percent", "decimals": 1}, "label": "Scraped rows that call fig.show()", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| calls `fig.show()` | 96.1% |"}},
  {"id": "scraped_reads", "value": 0.469, "format": {"kind": "percent", "decimals": 1}, "label": "Scraped rows that read a file or URL", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| reads a file or URL | 46.9% |"}},
  {"id": "scraped_columns", "value": 0.033, "format": {"kind": "percent", "decimals": 1}, "label": "Scraped prompts that mention columns", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| prompts mentioning columns | 3.3% |"}},
  {"id": "schemas", "value": 180, "format": {"kind": "number", "decimals": 0}, "label": "Table schemas Claude Haiku wrote", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| Schemas (180) |"}},
  {"id": "questions", "value": 2880, "format": {"kind": "number", "decimals": 0}, "label": "Questions Claude Haiku wrote", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| Questions (2,880) |"}},
  {"id": "targets_attempted", "value": 1920, "format": {"kind": "number", "decimals": 0}, "label": "Training questions Claude Sonnet wrote code answers for", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "1,897 kept of 1,920 attempted"}},
  {"id": "targets_kept", "value": 1897, "format": {"kind": "number", "decimals": 0}, "label": "Code answers that rendered in the sandbox and were kept", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "1,897 kept of 1,920 attempted"}},
  {"id": "test_questions", "value": 300, "format": {"kind": "number", "decimals": 0}, "label": "Frozen test questions", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| `data/testset.jsonl` | **300** |"}},
  {"id": "test_schemas", "value": 60, "format": {"kind": "number", "decimals": 0}, "label": "Schemas behind the frozen test questions, none seen in training", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "**FROZEN.** 60 schemas, no gold answers"}},
  {"id": "v1_train_rows", "value": 1929, "format": {"kind": "number", "decimals": 0}, "label": "lora-v1 training rows", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| `data/mlx/train.jsonl` | **1,929** |"}},
  {"id": "v1_synthetic_rows", "value": 1675, "format": {"kind": "number", "decimals": 0}, "label": "lora-v1 training rows from the synthetic pipeline", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| `data/mlx/train.jsonl` | **1,929** | 1,675 synthetic + 254 docs |"}},
  {"id": "v1_docs_rows", "value": 254, "format": {"kind": "number", "decimals": 0}, "label": "lora-v1 training rows rewritten from the Plotly docs to the app's contract", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| `data/mlx/train.jsonl` | **1,929** | 1,675 synthetic + 254 docs |"}},
  {"id": "v2_train_rows", "value": 7321, "format": {"kind": "number", "decimals": 0}, "label": "lora-v2 training rows", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "0 of lora-v2's 7,321"}},
  {"id": "v1_data_cost", "value": 5.4708, "format": {"kind": "usd", "decimals": 4}, "label": "Claude API cost of lora-v1's data", "source": {"kind": "quote", "file": "chartist-finetune/README.md", "quote": "| **Total** | | **$5.4708** |"}},
  {"id": "v2_data_cost", "value": 15.62, "format": {"kind": "usd", "decimals": 2}, "label": "Claude API cost of lora-v2's data", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "Claude API for the v2 data: $15.62"}},
  {"id": "gpu_rate", "value": 2.19, "format": {"kind": "usd", "decimals": 2}, "label": "Hourly price of the A100 80 GB on Runpod", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "| Pod | A100 SXM 80GB, **$2.19/hr**"}},
  {"id": "v1_pod_time", "value": 8668, "format": {"kind": "duration"}, "label": "lora-v1 pod time", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "Pod uptime 8,668 s (2 h 24 m)"}},
  {"id": "v1_loss_start", "value": 0.671, "format": {"kind": "number", "decimals": 3}, "label": "lora-v1 validation loss before training", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "**0.671 untrained"}},
  {"id": "v1_loss_end", "value": 0.1767, "format": {"kind": "number", "decimals": 4}, "label": "lora-v1 final validation loss", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "0.1771 → 0.1767 → 0.1767.**"}},
  {"id": "v1_cloud_cost", "value": 5.335408, "format": {"kind": "usd", "decimals": 6}, "label": "lora-v1 cloud cost, settled", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "| **cloud total** | **$5.335408** |"}},
  {"id": "v1_total_cost", "value": 10.81, "format": {"kind": "usd", "decimals": 2}, "label": "lora-v1 in all: data and cloud", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "the whole fine-tune cost **$10.81**"}},
  {"id": "v2_epochs", "value": 2, "format": {"kind": "number", "decimals": 0}, "label": "lora-v2 training epochs", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "2 epochs, 1,832 steps, 3.3 h"}},
  {"id": "v2_steps", "value": 1832, "format": {"kind": "number", "decimals": 0}, "label": "lora-v2 training steps", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "2 epochs, 1,832 steps, 3.3 h"}},
  {"id": "v2_hours", "value": 3.3, "format": {"kind": "number", "decimals": 1}, "label": "lora-v2 training hours", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "2 epochs, 1,832 steps, 3.3 h"}},
  {"id": "v2_loss_start", "value": 0.157, "format": {"kind": "number", "decimals": 3}, "label": "lora-v2 validation loss at the first evaluation", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "validation loss 0.157 -> 0.145"}},
  {"id": "v2_loss_end", "value": 0.126, "format": {"kind": "number", "decimals": 3}, "label": "lora-v2 best validation loss, the checkpoint kept", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "**0.126 (step 1500)**"}},
  {"id": "v2_cloud_cost", "value": 8.42, "format": {"kind": "usd", "decimals": 2}, "label": "lora-v2 cloud cost, settled", "source": {"kind": "quote", "file": "chartist-finetune/cloud/README.md", "quote": "= **$8.42**"}},
  {"id": "total_cost", "value": 34.85, "format": {"kind": "usd", "decimals": 0}, "label": "About this much made the data and trained both adapters", "source": {"kind": "sum", "of": ["v1_total_cost", "v2_data_cost", "v2_cloud_cost"]}},
  {"id": "max_repairs", "value": 2, "format": {"kind": "number", "decimals": 0}, "label": "Fixes the model gets for a chart before it is reported failed", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "at most `MAX_REPAIRS` = 2 times"}},
  {"id": "plan_tries", "value": 3, "format": {"kind": "number", "decimals": 0}, "label": "Tries the planner gets to pass the checks", "source": {"kind": "quote", "file": "AGENTS.md", "quote": "(at most 3 tries, best attempt kept)"}}
]
```

- [ ] **Step 5: Write `site/data/loss.json`:**

```json
{
  "v1": {
    "label": "lora-v1",
    "points": [0.671, 0.2441, 0.2194, 0.2016, 0.191, 0.1889, 0.1808, 0.1771, 0.1767, 0.1767],
    "source": {
      "file": "chartist-finetune/cloud/README.md",
      "quote": "0.671 untrained → 0.2441 → 0.2194 → 0.2016 → 0.1910 → 0.1889 → 0.1808 → 0.1771 → 0.1767 → 0.1767"
    }
  },
  "v2": {
    "label": "lora-v2",
    "steps": [300, 600, 900, 1200, 1500, 1800, 1832],
    "points": [0.1573, 0.1448, 0.1318, 0.1308, 0.1257, 0.1267, 0.1267],
    "source": {"file": "chartist-finetune/cloud/trainer_state_v2.json"}
  }
}
```

- [ ] **Step 6: Write `site/data/journey.json`.** Milestone texts carry no numbers; the numbers live in `stats.json`.

```json
[
  {"date": "2026-03-07", "commit": "35e0ce4", "subject": "add: README.md", "title": "First commit", "text": "A FastAPI backend and a Next.js front end that ask a model for a chart."},
  {"date": "2026-11-19", "commit": "ac9d3b2", "subject": "feat(finetune): generate execution-verified code targets with best-of-k", "title": "Training data", "text": "Claude writes the code answers; the app's own sandbox keeps only the ones that render."},
  {"date": "2026-11-20", "commit": "a0fd4d0", "subject": "feat(finetune): LoRA adapter trained and scored — render rate 7.7% to 91.3%", "title": "lora-v1", "text": "The first adapter, trained on a rented A100 and scored on the frozen test set."},
  {"date": "2026-11-21", "commit": "a91d276", "subject": "feat(dashboard): plan dashboards with the analyst and planner, checked by code", "title": "Dashboards planned by the model", "text": "An analyst and a planner plan whole dashboards; code checks every column against the real tables."},
  {"date": "2026-11-22", "commit": "7c8bdf1", "subject": "data(finetune): lora-v2 on the frozen 300 - 97.3% render, 87.0% right shape", "title": "lora-v2", "text": "Retrained with planning examples added; it plans and draws better than lora-v1."},
  {"date": "2026-11-23", "commit": "7deeaa3", "subject": "feat(chartist): no hardcoded charts; failed code goes back to the model", "title": "No hardcoded charts", "text": "Code that fails goes back to the model to fix; nothing else ever draws a chart."},
  {"date": "2026-11-25", "commit": "2d7af93", "subject": "feat(chartist): the drawing check sends back bars that repeat a category", "title": "The drawing check", "text": "Bars that stack raw rows go back to the model to be aggregated."}
]
```

- [ ] **Step 7: Run the tests**

Run: `cd site && npm test`
Expected: all pass: the 4 copies, 3 stats tests plus one per entry, 2 loss tests, and 7 journey tests plus the order test.

- [ ] **Step 8: Commit**

```bash
git add site/lib/stats.ts site/data/stats.json site/data/loss.json site/data/journey.json site/tests
git commit -m "feat(site): every number on the page, checked against the file that recorded it

stats.json keeps each raw value with its source: a JSON path, an exact
quote, or a sum. The page formats them; the tests read every value back.
The loss curves come from the run's README and the trainer's own log, and
each milestone from its commit.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: The hero: the app's own dot animation, drawing without end

**Files:**
- Create: `site/lib/site.ts`, `site/components/numbers.ts`, `site/components/icons.tsx`, `site/components/dot-hero.tsx`, `site/components/hero.tsx`
- Modify: `site/app/page.tsx` (replace the stub)
- Local only: `.claude/launch.json` (the `site` dev server, for the browser check). Nothing under `.claude/` is tracked, so it is not committed.

**Interfaces:**
- Consumes: `animateDots` from `site/lib/dot-draw.ts` (Task 7's copy of Task 2's file); `findStat` and `formatStat` from `site/lib/stats.ts`, and the ids in `site/data/stats.json` (Task 8).
- Produces:
  - `site/lib/site.ts`: `REPO_URL`, `AUTHOR = { handle, url }`, `fileUrl(path: string): string`, `commitUrl(hash: string): string`.
  - `site/components/numbers.ts`: `stat(id: string, decimals?: number): string` and `statSource(id: string): string | null`.
  - `site/components/icons.tsx`: `GitHubMark`, `CodeIcon` (props `size?`).
  - `<Hero />` and `<DotHero />`.

The page's components are presentational and are checked by build, lint and the browser. The logic they use (`formatStat`, `animateDots`'s per-frame `drawDots`) is unit-tested in Tasks 2 and 8.

- [ ] **Step 1: Links in one place.** `site/lib/site.ts`:

```ts
/* Where the page links. Part 2 (open source) renames the repository: change
   REPO_URL then, and every link follows. Import-free. */
export const REPO_URL = "https://github.com/tukka25/BYD";
export const AUTHOR = { handle: "@tukka25", url: "https://github.com/tukka25" };

export const fileUrl = (path: string): string => `${REPO_URL}/blob/main/${path}`;
export const commitUrl = (hash: string): string => `${REPO_URL}/commit/${hash}`;
```

- [ ] **Step 2: Numbers for components.** `site/components/numbers.ts`:

```ts
import stats from "@/data/stats.json";
import { findStat, formatStat, type Stat } from "@/lib/stats";

const ALL = stats as unknown as Stat[];

/** A number from data/stats.json as the page shows it; `decimals` shows fewer places. */
export function stat(id: string, decimals?: number): string {
  return formatStat(findStat(ALL, id), decimals);
}

/** The repository file a number came from, for a link beside it. A sum has none of its own. */
export function statSource(id: string): string | null {
  const source = findStat(ALL, id).source;
  return source.kind === "sum" ? null : source.file;
}
```

- [ ] **Step 3: Icons.** `site/components/icons.tsx`:

```tsx
import type { SVGProps } from "react";

type IconProps = Omit<SVGProps<SVGSVGElement>, "width" | "height"> & { size?: number };

/* GitHub's mark (Octicons mark-github, MIT), on the repository link. */
export function GitHubMark({ size = 16, ...props }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/* lucide's code-xml, as the app's "Show the code that drew this" button draws it. */
export function CodeIcon({ size = 15, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m18 16 4-4-4-4" />
      <path d="m6 8-4 4 4 4" />
      <path d="m14.5 4-5 16" />
    </svg>
  );
}
```

- [ ] **Step 4: The animation.** `site/components/dot-hero.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";
import { animateDots } from "@/lib/dot-draw";

/* The build loader's animation (lib/dot-draw.ts, byte-identical to byd-web's),
   drawn larger and looping through every chart shape without end. It draws as
   if 320 px wide, the loader's size, then scales up, so the dots keep their
   proportions. It pauses off screen and in a hidden tab; with reduced motion it
   holds one still shape. */
export function DotHero() {
  const canvas = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    return animateDots(node, { logicalWidth: 320 });
  }, []);

  return (
    <div className="aspect-[5/3] w-full overflow-hidden rounded-[var(--r-panel)] bg-surface shadow-[var(--lift-1)]">
      <canvas ref={canvas} className="size-full" aria-hidden />
    </div>
  );
}
```

- [ ] **Step 5: The hero.** `site/components/hero.tsx`:

```tsx
import { DotHero } from "@/components/dot-hero";
import { GitHubMark } from "@/components/icons";
import { stat } from "@/components/numbers";
import { REPO_URL } from "@/lib/site";

export function Hero() {
  return (
    <header className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-12 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pb-24 lg:pt-20">
      <div>
        <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-pine">Fine-tuned · runs on your Mac</p>
        <h1 className="mt-4 font-display text-[44px] font-bold leading-[1.02] sm:text-[60px]">PromptDash</h1>
        <p className="mt-5 max-w-xl text-[17px] leading-relaxed sm:text-[19px]">
          Ask for a dashboard in plain words. A 9B model fine-tuned to write Plotly draws every chart, on your own
          machine.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <a
            href={REPO_URL}
            className="inline-flex h-11 items-center gap-2 rounded-[var(--r-pill)] bg-pine px-5 text-[15px] font-semibold text-white shadow-[var(--lift-1)] transition-colors hover:bg-[var(--pine-press)]"
          >
            <GitHubMark />
            View on GitHub
          </a>
          <a
            href="#dashboards"
            className="inline-flex h-11 items-center rounded-[var(--r-pill)] bg-surface px-5 text-[15px] font-semibold text-ink ring-1 ring-inset ring-hairline transition-colors hover:bg-sunken"
          >
            See three dashboards
          </a>
        </div>
        <dl className="mt-10 grid max-w-xl gap-3 sm:grid-cols-3">
          <Figure label="of chart scripts run" value={`${stat("base_render_mac", 0)} → ${stat("v2_render_mac", 0)}`} />
          <Figure
            label="draw the right kind of chart"
            value={`${stat("base_shape_mac", 0)} → ${stat("v2_shape_mac", 0)}`}
          />
          <Figure label="for the data and both training runs" value={`≈ ${stat("total_cost")}`} />
        </dl>
        <p className="mt-3 max-w-xl text-[12px] leading-relaxed text-muted">
          Base Qwen3.5-9B with thinking off → lora-v2, on the same {stat("test_questions")} frozen test questions,
          4-bit on a Mac.
        </p>
      </div>
      <DotHero />
    </header>
  );
}

/* Label first in the DOM, as a definition list wants; on wider screens the
   number shows above it. On a phone each figure is one row. */
function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 rounded-[var(--r-card)] bg-surface px-4 py-3 shadow-[var(--lift-1)] sm:flex-col-reverse sm:items-start sm:justify-end sm:py-4">
      <dt className="text-[12.5px] leading-snug text-muted">{label}</dt>
      <dd className="font-display text-[20px] font-bold leading-tight text-ink tabular sm:text-[24px]">{value}</dd>
    </div>
  );
}
```

- [ ] **Step 6: The page.** Replace `site/app/page.tsx`:

```tsx
import { Hero } from "@/components/hero";

export default function Home() {
  return (
    <main>
      <Hero />
    </main>
  );
}
```

- [ ] **Step 7: Lint, test and build**

Run: `cd site && npm run lint && npm test && npm run build`
Expected: no lint errors, every test passes, and the build exports `/`.

- [ ] **Step 8 (controller): Look at it.** Add the dev server to `.claude/launch.json` (create the file if it does not exist):

```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "site", "runtimeExecutable": "npm", "runtimeArgs": ["--prefix", "site", "run", "dev"], "port": 3100 }
  ]
}
```

  Start it with `preview_start` (name `site`). Check at desktop width and with the `mobile` preset:
  - the dots morph through the shapes without stopping, and are crisp;
  - the three figures read `<base> → 94%`, `<base> → 82%` and `≈ $35`;
  - nothing scrolls sideways at phone width.

  Reset the viewport to `desktop` afterwards. Reduced motion cannot be emulated in the pane: its path is unit-tested (Task 2), and the owner can confirm it with macOS Reduce Motion on.

- [ ] **Step 9: Commit**

```bash
git add site/lib/site.ts site/components site/app/page.tsx
git commit -m "feat(site): the hero, with the build loader's own dot animation

The canvas runs a byte-identical copy of byd-web's lib/dot-draw.ts, drawn
at the loader's 320 px and scaled up, so it is the same animation. The
three headline numbers come from stats.json: base with thinking off to
lora-v2 on the frozen 300, and the cost of both adapters.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: The three dashboards, live, in the app's View mode

The section's HTML comes from the build: each card's title and frame at its saved size, the intro note, the prompt and the provenance. Each chart's figure and Plotly load when the card first comes within 600 px of the screen. One dashboard shows at a time, behind tabs.

**Files:**
- Create: `site/lib/dashboard.ts`
- Create: `site/components/plotly.ts`, `site/components/dashboard-data.ts`, `site/components/lazy-chart.tsx`, `site/components/dashboard-card.tsx`, `site/components/dashboard-view.tsx`, `site/components/dashboard-tabs.tsx`, `site/components/dashboards.tsx`
- Modify: `site/app/page.tsx`
- Test: `site/tests/dashboard.test.mts`

**Interfaces:**
- Consumes: the dashboard files from Task 6 (shared format above); `themed` from `site/lib/plot-theme.ts`; `toHtml` from `site/lib/rich-text.ts`; `CodeIcon` from Task 9.
- Produces:
  - `site/lib/dashboard.ts`: `type Dashboard`, `type DashboardBlock`, `type DashboardSource`, `COLUMNS = 12`, `ROW_HEIGHT = 44`, `GAP = 16`, `MAX_BYTES = 1_500_000`, `gridPlacement(block)`, `blockHeight(h)`, `isIndicator(block)`, `sourceKinds(dashboard)`, `validateDashboard(value: unknown, bytes: number): string[]`.
  - `<Dashboards />`: the section, with anchor `#dashboards`.
- If Task 1 chose the shop demo, use `shop.json` in place of `spotify.json` in `dashboards.tsx` and `dashboard-data.ts`.

What the four copies do not carry, and this task supplies: the canvas grid (rows of 44 px, gaps of 16 px, from `report-canvas.tsx`) as a CSS grid. The app's vertical compaction is not reproduced. The saved layout is already packed by the app's `lay_out`, so its positions are drawn as they are.

- [ ] **Step 1: Write the failing test** `site/tests/dashboard.test.mts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import {
  blockHeight,
  gridPlacement,
  isIndicator,
  sourceKinds,
  validateDashboard,
  type Dashboard,
} from "../lib/dashboard.ts";

function sample(): Dashboard {
  return {
    name: "sample",
    title: "Sample",
    prompt: "show me sales",
    currency: "",
    sources: [
      { name: "sales.csv", kind: "file", rows: 10, url: "https://example.org/sales.csv", licence: "CC0 1.0",
        licence_url: "", note: "A test file." },
    ],
    blocks: [
      { kind: "text", title: "About this data", chart_type: null, figure: null, text_body: "<p>Ten rows.</p>",
        code: null, x: 0, y: 0, w: 12, h: 3 },
      { kind: "chart", title: "Sales by month", chart_type: "line", figure: { data: [{ type: "scatter" }] },
        text_body: null, code: "fig = px.line(df)", x: 0, y: 3, w: 8, h: 8 },
      { kind: "metric", title: "Total sales", chart_type: "kpi", figure: { data: [{ type: "indicator" }] },
        text_body: null, code: "fig = go.Figure()", x: 8, y: 3, w: 4, h: 3 },
    ],
    build: { charts_planned: 2, charts_drawn: 2, skipped: [], missing_kinds: [], seconds: 60, prompts_tried: 1 },
    model: { base: "models/qwen3.5-9b-4bit", adapter: "runs/adapters-mlx-v2", label: "lora-v2" },
    app_commit: "abc1234",
    generated_at: "2026-11-26T09:30:00Z",
  };
}

const problems = (dashboard: Dashboard, bytes = 1000) => validateDashboard(dashboard, bytes).join("; ");

test("a well-formed dashboard has no problems", () => {
  assert.equal(problems(sample()), "");
});

test("a broken file is refused, in words", () => {
  const overflow = sample();
  overflow.blocks[2].w = 5;
  assert.match(problems(overflow), /Total sales: outside the 12-column grid/);

  const empty = sample();
  empty.blocks[1].figure = null;
  assert.match(problems(empty), /Sales by month: no figure/);

  const miscounted = sample();
  miscounted.build.charts_drawn = 3;
  assert.match(problems(miscounted), /build says 3 charts drawn; the file holds 2/);

  const unsourced = sample();
  unsourced.sources[0].licence = "";
  assert.match(problems(unsourced), /source sales.csv has no licence/);

  assert.match(problems(sample(), 1_500_000), /at or over 1500000 bytes/);
});

test("blocks sit where the app saved them, at the canvas's row height and gap", () => {
  assert.deepEqual(gridPlacement({ x: 8, y: 3, w: 4, h: 3 }), { gridColumn: "9 / span 4", gridRow: "4 / span 3" });
  assert.equal(blockHeight(8), 8 * 44 + 7 * 16);
});

test("an all-indicator figure is a stat card", () => {
  const [, chart, metric] = sample().blocks;
  assert.equal(isIndicator(metric), true);
  assert.equal(isIndicator(chart), false);
});

test("a tab names the kinds of source behind its dashboard", () => {
  const file = sample().sources[0];
  assert.equal(sourceKinds({ sources: [{ ...file, name: "listings.xlsx" }, file] }), "Excel + CSV");
  assert.equal(sourceKinds({ sources: [{ ...file, kind: "database", name: "spotify.tracks" }] }), "Postgres");
});

const DIR = new URL("../data/dashboards/", import.meta.url);
const files = readdirSync(DIR).filter((name) => name.endsWith(".json"));

test("three dashboards are on the page, each drawn by lora-v2", () => {
  assert.equal(files.length, 3, files.join(", "));
  for (const name of files) {
    assert.equal(JSON.parse(readFileSync(new URL(name, DIR), "utf8")).model.label, "lora-v2", name);
  }
});

for (const name of files) {
  test(`${name} is fit to show`, () => {
    const path = new URL(name, DIR);
    assert.deepEqual(validateDashboard(JSON.parse(readFileSync(path, "utf8")), statSync(path).size), []);
  });
}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd site && npm test`
Expected: FAIL: `Cannot find module '.../lib/dashboard.ts'`.

- [ ] **Step 3: Write `site/lib/dashboard.ts`:**

```ts
/* The dashboard files the page shows (data/dashboards/*.json, written by
   backend/scripts/make_showcase.py), and where their blocks sit. Import-free,
   so Node's test runner can load it. */

export type BlockKind = "text" | "chart" | "metric";

export type DashboardBlock = {
  kind: BlockKind;
  title: string;
  chart_type: string | null;
  figure: { data?: unknown[]; layout?: Record<string, unknown> } | null;
  text_body: string | null;
  code: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type DashboardSource = {
  name: string;
  kind: "file" | "database";
  rows: number;
  url: string;
  licence: string;
  licence_url: string;
  note: string;
};

export type Dashboard = {
  name: string;
  title: string;
  prompt: string;
  currency: string;
  sources: DashboardSource[];
  blocks: DashboardBlock[];
  build: {
    charts_planned: number;
    charts_drawn: number;
    skipped: { label: string; reason: string }[];
    missing_kinds: string[];
    seconds: number;
    prompts_tried: number;
  };
  model: { base: string; adapter: string; label: string };
  app_commit: string;
  generated_at: string;
};

export const COLUMNS = 12;
export const ROW_HEIGHT = 44; // the canvas's react-grid-layout rowHeight (report-canvas.tsx)
export const GAP = 16; // and its margin
export const MAX_BYTES = 1_500_000;

/** Where a block sits in the 12-column grid: the app's saved x, y, w and h. */
export function gridPlacement(block: Pick<DashboardBlock, "x" | "y" | "w" | "h">) {
  return { gridColumn: `${block.x + 1} / span ${block.w}`, gridRow: `${block.y + 1} / span ${block.h}` };
}

/** A block's height in pixels, as the canvas draws it: h rows and the gaps between them. */
export function blockHeight(h: number): number {
  return h * ROW_HEIGHT + (h - 1) * GAP;
}

/** An all-indicator figure is a stat card, drawn without plot chrome, as in the app. */
export function isIndicator(block: Pick<DashboardBlock, "figure">): boolean {
  const data = (block.figure?.data ?? []) as Array<{ type?: string }>;
  return data.length > 0 && data.every((trace) => trace?.type === "indicator");
}

/** "Excel + CSV", "Postgres", "CSV": what a dashboard was built from. */
export function sourceKinds(dashboard: Pick<Dashboard, "sources">): string {
  const kinds = dashboard.sources.map((source) => {
    if (source.kind === "database") return "Postgres";
    return /\.xlsx?$/i.test(source.name) ? "Excel" : "CSV";
  });
  return [...new Set(kinds)].join(" + ");
}

/** What is wrong with a dashboard file, in words. Empty when it is fit to show. */
export function validateDashboard(value: unknown, bytes: number): string[] {
  if (!value || typeof value !== "object") return ["not a JSON object"];
  const d = value as Partial<Dashboard>;
  const problems: string[] = [];
  if (bytes >= MAX_BYTES) problems.push(`${bytes} bytes, at or over ${MAX_BYTES} bytes`);
  for (const key of ["name", "title", "prompt", "app_commit", "generated_at"] as const) {
    if (typeof d[key] !== "string" || !d[key]) problems.push(`no ${key}`);
  }
  if (typeof d.currency !== "string") problems.push("no currency (an empty string when the source names none)");
  if (!Array.isArray(d.sources) || d.sources.length === 0) problems.push("no sources");
  for (const source of d.sources ?? []) {
    for (const key of ["name", "url", "licence", "note"] as const) {
      if (!source[key]) problems.push(`source ${source.name || "?"} has no ${key}`);
    }
    if (!(source.rows > 0)) problems.push(`source ${source.name} has no row count`);
    if (source.kind !== "file" && source.kind !== "database") problems.push(`source ${source.name} is a ${source.kind}`);
  }
  if (!Array.isArray(d.blocks) || d.blocks.length === 0) problems.push("no blocks");
  for (const block of d.blocks ?? []) {
    const name = block.title || "an untitled block";
    if (!["text", "chart", "metric"].includes(block.kind)) problems.push(`${name}: kind ${block.kind}`);
    if (block.kind === "text" && !block.text_body) problems.push(`${name}: a note with no text`);
    if (block.kind !== "text" && !Array.isArray(block.figure?.data)) problems.push(`${name}: no figure`);
    const inside = block.x >= 0 && block.y >= 0 && block.w >= 1 && block.h >= 1 && block.x + block.w <= COLUMNS;
    if (!inside) problems.push(`${name}: outside the 12-column grid`);
  }
  if (!d.build) {
    problems.push("no build record");
  } else {
    const drawn = (d.blocks ?? []).filter((block) => block.kind !== "text").length;
    if (d.build.charts_drawn !== drawn) {
      problems.push(`build says ${d.build.charts_drawn} charts drawn; the file holds ${drawn}`);
    }
    if (!(d.build.prompts_tried >= 1)) problems.push("build.prompts_tried is under 1");
  }
  if (!d.model?.label) problems.push("no model label");
  return problems;
}
```

- [ ] **Step 4: Run the tests**

Run: `cd site && npm test`
Expected: all pass, including the three real dashboard files from Task 6.

- [ ] **Step 5: Plotly, loaded once.** `site/components/plotly.ts`:

```ts
/* Plotly, imported once, when the first chart comes near the screen: it is the
   largest thing on the page, and a visitor reads the top first. */
export type PlotlyApi = {
  react: (el: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
  Plots: { resize: (el: HTMLElement) => void };
  purge: (el: HTMLElement) => void;
};

let loading: Promise<PlotlyApi> | null = null;

export function loadPlotly(): Promise<PlotlyApi> {
  loading ??= import("plotly.js-dist-min").then((mod) => (mod.default ?? mod) as unknown as PlotlyApi);
  return loading;
}
```

- [ ] **Step 6: The figures, as separate chunks.** `site/components/dashboard-data.ts`:

```ts
import type { Dashboard } from "@/lib/dashboard";

/* Each dashboard file becomes its own chunk, fetched when one of its charts
   first nears the screen, so the figures stay out of the page's first load.
   The cards themselves are in the HTML from the build. */
export const DASHBOARD_DATA: Record<string, () => Promise<Dashboard>> = {
  airbnb: () => import("@/data/dashboards/airbnb.json").then((mod) => mod.default as unknown as Dashboard),
  spotify: () => import("@/data/dashboards/spotify.json").then((mod) => mod.default as unknown as Dashboard),
  netflix: () => import("@/data/dashboards/netflix.json").then((mod) => mod.default as unknown as Dashboard),
};
```

- [ ] **Step 7: One chart.** `site/components/lazy-chart.tsx`:

```tsx
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

  return (
    <div className="relative size-full">
      <div ref={host} className={`size-full ${indicator ? "[&_.cartesianlayer]:hidden" : ""}`} />
      {view.phase === "waiting" ? (
        <div className="absolute inset-0 rounded-[var(--r-card)] bg-sunken/50" aria-hidden />
      ) : null}
      {view.phase === "failed" ? (
        <p className="absolute inset-0 grid place-items-center p-4 text-center text-[13px] text-muted">
          {view.message}
        </p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 8: A card, as the app's View mode draws it.** `site/components/dashboard-card.tsx`:

```tsx
"use client";

import { useState, type ReactNode } from "react";
import { CodeIcon } from "@/components/icons";

/* A block as the app's View mode draws it (BlockFrame in report-canvas.tsx):
   the title, the chart or note, and the button that shows the code the model
   wrote. As in the app, showing the code replaces the chart until it is hidden. */
export function DashboardCard({ title, code, children }: { title: string; code: string | null; children: ReactNode }) {
  const [showCode, setShowCode] = useState(false);
  const label = showCode ? "Hide the code" : "Show the code that drew this";

  return (
    <section
      aria-label={title}
      className="flex h-full flex-col overflow-hidden rounded-[var(--r-panel)] bg-surface shadow-[var(--lift-1)]"
    >
      <header className="flex items-start gap-2 px-5 pt-4">
        <h3 className="min-w-0 flex-1 truncate font-display text-[15px] font-semibold leading-tight text-ink" title={title}>
          {title}
        </h3>
        {code ? (
          <button
            type="button"
            onClick={() => setShowCode((shown) => !shown)}
            aria-pressed={showCode}
            aria-label={label}
            title={label}
            className={`grid size-8 shrink-0 place-items-center rounded-[var(--r-control)] transition-colors ${
              showCode ? "bg-pine-wash text-pine" : "text-muted hover:bg-sunken hover:text-ink"
            }`}
          >
            <CodeIcon />
          </button>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 px-3 pb-3 pt-2">
        {showCode && code ? (
          <pre className="size-full overflow-auto rounded-[var(--r-card)] bg-inverse p-4 font-mono text-[11.5px] leading-relaxed text-on-dark">
            <code>{code}</code>
          </pre>
        ) : (
          children
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 9: A dashboard, its prompt and its provenance.** `site/components/dashboard-view.tsx`:

```tsx
import type { CSSProperties } from "react";
import { DashboardCard } from "@/components/dashboard-card";
import { LazyChart } from "@/components/lazy-chart";
import { blockHeight, gridPlacement, isIndicator, type Dashboard } from "@/lib/dashboard";
import { toHtml } from "@/lib/rich-text";

/* The saved 12-column grid at the canvas's row height and gap. Under 768 px it
   is one column in the saved order, each chart at full width and its saved
   height; notes take the height their text needs. */
export function DashboardView({ dashboard }: { dashboard: Dashboard }) {
  return (
    <div>
      <div className="flex flex-col gap-4 md:grid md:auto-rows-[44px] md:grid-cols-12">
        {dashboard.blocks.map((block, index) => (
          <div
            key={`${block.y}-${block.x}`}
            style={{ ...gridPlacement(block), "--block-h": `${blockHeight(block.h)}px` } as CSSProperties}
            className={block.kind === "text" ? "md:h-auto" : "h-[var(--block-h)] md:h-auto"}
          >
            <DashboardCard title={block.title} code={block.code}>
              {block.kind === "text" ? (
                <div
                  className="rich-text size-full overflow-auto px-2 py-1 text-sm leading-relaxed text-body"
                  // Sanitised by the app's own sanitiser (lib/rich-text.ts), as the app does on render.
                  dangerouslySetInnerHTML={{ __html: toHtml(block.text_body) }}
                />
              ) : (
                <LazyChart
                  dashboard={dashboard.name}
                  index={index}
                  currency={dashboard.currency}
                  indicator={isIndicator(block)}
                />
              )}
            </DashboardCard>
          </div>
        ))}
      </div>
      <PromptBox dashboard={dashboard} />
      <Provenance dashboard={dashboard} />
    </div>
  );
}

/* The prompt, frozen below its dashboard: the app's brief box, read-only. It
   stays in view while you scroll through the dashboard it built. */
function PromptBox({ dashboard }: { dashboard: Dashboard }) {
  const { build } = dashboard;
  const rephrased = build.prompts_tried - 1;
  return (
    <div className="sticky bottom-4 z-10 mt-6">
      <div className="mx-auto max-w-3xl rounded-[var(--r-panel)] bg-surface p-3 shadow-[var(--lift-2)]">
        <p className="px-1 text-[13px] font-semibold text-ink">What should this dashboard be about?</p>
        <p className="mt-1.5 rounded-[var(--r-control)] px-3.5 py-3 text-sm text-ink ring-1 ring-inset ring-hairline">
          {dashboard.prompt}
        </p>
        <p className="mt-2 px-1 text-[12px] text-muted tabular">
          Sent as typed · {build.charts_drawn} of {build.charts_planned} charts drawn · {Math.round(build.seconds)} s on
          a Mac
          {rephrased > 0 ? ` · after ${rephrased} rephrasing${rephrased > 1 ? "s" : ""}` : ""}
        </p>
      </div>
    </div>
  );
}

function Provenance({ dashboard }: { dashboard: Dashboard }) {
  const notes = [...new Set(dashboard.sources.map((source) => source.note))].join(" ");
  const skipped = dashboard.build.skipped;
  const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";
  return (
    <div className="mt-4 space-y-1 px-1 text-[12.5px] leading-relaxed text-muted">
      <p>
        Data:{" "}
        {dashboard.sources.map((source, i) => (
          <span key={source.name}>
            {i > 0 ? "; " : ""}
            <a href={source.url} className={link}>
              {source.name}
            </a>{" "}
            ({source.rows.toLocaleString("en-US")} rows,{" "}
            {source.licence_url ? (
              <a href={source.licence_url} className={link}>
                {source.licence}
              </a>
            ) : (
              source.licence
            )}
            )
          </span>
        ))}
        . {notes}
      </p>
      <p>
        Drawn by {dashboard.model.label}, unedited, on {dashboard.generated_at.slice(0, 10)}.
        {skipped.length
          ? ` ${skipped.length} planned chart${skipped.length > 1 ? "s" : ""} could not be drawn: ${skipped
              .map((item) => item.label)
              .join(", ")}.`
          : ""}
      </p>
    </div>
  );
}
```

- [ ] **Step 10: Tabs.** `site/components/dashboard-tabs.tsx`:

```tsx
"use client";

import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export type Tab = { id: string; label: string; detail: string };

/* One dashboard at a time. The hidden ones stay in the page's HTML, and their
   charts load the first time their tab opens. Arrow keys move between tabs. */
export function DashboardTabs({ tabs, children }: { tabs: Tab[]; children: ReactNode[] }) {
  const [active, setActive] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (active + step + tabs.length) % tabs.length;
    setActive(next);
    buttons.current[next]?.focus();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label="Dashboards"
        onKeyDown={onKeyDown}
        className="inline-flex max-w-full gap-1 overflow-x-auto rounded-[var(--r-pill)] bg-sunken p-1"
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
            aria-selected={index === active}
            tabIndex={index === active ? 0 : -1}
            onClick={() => setActive(index)}
            className={`whitespace-nowrap rounded-[var(--r-pill)] px-4 py-2 text-[13.5px] font-semibold transition-colors ${
              index === active ? "bg-surface text-ink shadow-[var(--lift-1)]" : "text-muted hover:text-ink"
            }`}
          >
            {tab.label} <span className="font-normal text-muted">· {tab.detail}</span>
          </button>
        ))}
      </div>
      {children.map((child, index) => (
        <div
          key={tabs[index].id}
          role="tabpanel"
          id={`panel-${tabs[index].id}`}
          aria-labelledby={`tab-${tabs[index].id}`}
          hidden={index !== active}
          className="mt-6"
        >
          {child}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 11: The section.** `site/components/dashboards.tsx`:

```tsx
import airbnb from "@/data/dashboards/airbnb.json";
import netflix from "@/data/dashboards/netflix.json";
import spotify from "@/data/dashboards/spotify.json";
import { DashboardTabs } from "@/components/dashboard-tabs";
import { DashboardView } from "@/components/dashboard-view";
import { sourceKinds, validateDashboard, type Dashboard } from "@/lib/dashboard";

// The footer credits the data from these files too.
export const DASHBOARDS = [airbnb, spotify, netflix] as unknown as Dashboard[];

// A broken file fails the build, as the tests would.
for (const dashboard of DASHBOARDS) {
  const problems = validateDashboard(dashboard, new TextEncoder().encode(JSON.stringify(dashboard)).length);
  if (problems.length) throw new Error(`data/dashboards/${dashboard.name}.json: ${problems.join("; ")}`);
}

export function Dashboards() {
  return (
    <section id="dashboards" className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
      <h2 className="font-display text-[30px] font-bold leading-tight sm:text-[36px]">Three prompts, three dashboards</h2>
      <p className="mt-3 max-w-2xl text-[16px] leading-relaxed">
        Each is the app&apos;s own output, unedited: one prompt typed as a person would, and every chart lora-v2
        planned and drew from it. The code button on a chart shows what the model wrote.
      </p>
      <div className="mt-8">
        <DashboardTabs tabs={DASHBOARDS.map((d) => ({ id: d.name, label: d.title, detail: sourceKinds(d) }))}>
          {DASHBOARDS.map((d) => (
            <DashboardView key={d.name} dashboard={d} />
          ))}
        </DashboardTabs>
      </div>
    </section>
  );
}
```

- [ ] **Step 12: Put it on the page.** `site/app/page.tsx`:

```tsx
import { Dashboards } from "@/components/dashboards";
import { Hero } from "@/components/hero";

export default function Home() {
  return (
    <main>
      <Hero />
      <Dashboards />
    </main>
  );
}
```

- [ ] **Step 13: Lint, test and build**

Run: `cd site && npm run lint && npm test && npm run build`
Expected: no lint errors; all tests pass; the build exports `/`. In `out/_next/static/chunks/`, the dashboards' figures and Plotly are separate chunks, not in the page's first chunk. Check with `ls -S out/_next/static/chunks | head`.

- [ ] **Step 14 (controller): Look at it** with `preview_start` (name `site`):
  - Plotly is requested only as the dashboards section comes near: check with `read_network_requests`.
  - In each tab, every chart draws. Hover shows values; dragging does not zoom; there is no mode bar.
  - KPI blocks read as the app's stat cards. The code button shows the model's code.
  - The prompt box stays in view while scrolling through a dashboard.
  - Compare one dashboard with the same report in the app's View mode (account `showcase@example.com`): same charts, colours and number formats.
  - With the `mobile` preset: one column, nothing scrolls sideways. Reset the viewport to `desktop` afterwards.

- [ ] **Step 15: Commit**

```bash
git add site/lib/dashboard.ts site/components site/app/page.tsx site/tests/dashboard.test.mts
git commit -m "feat(site): the three dashboards, live, in the app's View mode

The build writes each card's title, frame and note into the HTML; the
figure and Plotly load when the card nears the screen, drawn with the
app's re-theme, hover on and zoom off. The prompt sits below its dashboard,
frozen, with what the build drew and how long it took. A broken file fails
the build and the tests.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: The story: journey, problem, data, training, results, how it works, run it, footer

Each section is a few technical sentences and one figure, table or diagram. Every number comes from `stat()` or `<Num>`, so it comes from `stats.json`; milestones come from `journey.json`, and loss points from `loss.json`.

Two corrections to the spec's outline, both true to the code:
- **How it works:** on a dashboard the planner writes each chart's title. The narrator titles a single chart asked for in the ask bar. The diagram shows the dashboard path and says this in one line.
- **The data:** the scraped docs were not set aside. 254 of lora-v1's 1,929 rows are docs examples rewritten to the app's contract, and the pipeline says so.

**Files:**
- Create: `site/components/section.tsx`, `site/components/num.tsx`, `site/components/journey.tsx`, `site/components/problem.tsx`, `site/components/data-pipeline.tsx`, `site/components/loss-chart.tsx`, `site/components/training.tsx`, `site/components/results.tsx`, `site/components/how-it-works.tsx`, `site/components/run-it.tsx`, `site/components/footer.tsx`
- Modify: `site/components/numbers.ts` (add `statLabel`), `site/app/page.tsx`

**Interfaces:**
- Consumes: `stat`, `statSource` (Task 9); `fileUrl`, `commitUrl`, `REPO_URL`, `AUTHOR` (Task 9); `DASHBOARDS` (Task 10); `data/journey.json`, `data/loss.json` (Task 8).
- Produces: `statLabel(id: string): string`; `<Num id decimals? />`; `<Section id kicker title>` and `<Lede>`; one component per section.

The validation-loss charts follow the chart rules:
- one series each, so no legend; the caption names it;
- a 2 px line, and 8 px markers with a 2 px surface ring;
- only the highest and lowest values labelled, in ink colours, never the series colour;
- a native tooltip on a 22 px hit target per point, and the values again as a table for screen readers.

The two runs score against different validation sets, so each gets its own chart and axis, and the text says the curves do not compare.

- [ ] **Step 1: A label lookup.** Append to `site/components/numbers.ts`:

```ts
/** What a number measures, for the title of its link. */
export function statLabel(id: string): string {
  return findStat(ALL, id).label;
}
```

- [ ] **Step 2: Shared pieces.** `site/components/section.tsx`:

```tsx
import type { ReactNode } from "react";

/* One part of the story: a short title, a few technical sentences, then one
   figure, table or diagram. */
export function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-6xl px-4 py-14 sm:px-8 sm:py-16">
      <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-pine">{kicker}</p>
      <h2 className="mt-3 max-w-3xl font-display text-[28px] font-bold leading-tight sm:text-[34px]">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export function Lede({ children }: { children: ReactNode }) {
  return <p className="max-w-3xl text-[16px] leading-relaxed">{children}</p>;
}
```

`site/components/num.tsx`:

```tsx
import { stat, statLabel, statSource } from "@/components/numbers";
import { fileUrl } from "@/lib/site";

/* A number that links to the file that recorded it; its title says what it measures. */
export function Num({ id, decimals }: { id: string; decimals?: number }) {
  const file = statSource(id);
  const text = stat(id, decimals);
  if (!file) return <span title={statLabel(id)}>{text}</span>;
  return (
    <a
      href={fileUrl(file)}
      title={statLabel(id)}
      className="underline decoration-hairline-strong decoration-dotted underline-offset-4 transition-colors hover:decoration-pine"
    >
      {text}
    </a>
  );
}
```

- [ ] **Step 3: Journey.** `site/components/journey.tsx`:

```tsx
import journey from "@/data/journey.json";
import { Section } from "@/components/section";
import { commitUrl } from "@/lib/site";

type Milestone = { date: string; commit: string; subject: string; title: string; text: string };

export function Journey() {
  return (
    <Section id="journey" kicker="Journey" title="From a first commit to a fine-tuned chartist">
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(journey as Milestone[]).map((milestone) => (
          <li key={milestone.commit} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-muted tabular">{milestone.date}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{milestone.title}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{milestone.text}</p>
            <a
              href={commitUrl(milestone.commit)}
              className="mt-3 inline-block font-mono text-[11.5px] text-pine underline decoration-pine/30 underline-offset-2"
            >
              {milestone.commit}
            </a>
          </li>
        ))}
      </ol>
    </Section>
  );
}
```

- [ ] **Step 4: The problem.** `site/components/problem.tsx`:

```tsx
import type { ReactNode } from "react";
import { stat } from "@/components/numbers";
import { Lede, Section } from "@/components/section";

const code = (text: string) => <code className="font-mono text-[12.5px]">{text}</code>;

export function Problem() {
  const rows: Array<[ReactNode, string, string]> = [
    [<>ends with {code("print(fig.to_json())")}</>, stat("scraped_json_print"), "every time"],
    [<>calls {code("fig.show()")}</>, stat("scraped_show"), "never"],
    ["reads a file or URL", stat("scraped_reads"), "never"],
    ["the prompt names the columns", stat("scraped_columns"), "every time"],
  ];
  return (
    <Section id="problem" kicker="The problem" title="A capable model that writes essays, not charts">
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-4">
          <Lede>
            Out of the box, Qwen3.5-9B opens every answer with a reasoning essay. On the {stat("test_questions")} frozen
            test questions, at full precision, {stat("base_render_pod")} of its chart scripts run.
          </Lede>
          <Lede>
            With thinking off it writes code: on a Mac at 4-bit, {stat("base_render_mac")} of its scripts run and{" "}
            {stat("base_shape_mac")} draw the right kind of chart. Most of the rest fail at run time or ask for columns
            that do not exist.
          </Lede>
          <Lede>
            And the examples to hand taught the opposite of what the app needs: {stat("scraped_rows")} rows scraped from
            plotly.com/python, measured against the app&apos;s contract.
          </Lede>
        </div>
        <div className="self-start overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
          <table className="w-full text-left text-[14px]">
            <thead>
              <tr className="border-b text-[12px] uppercase tracking-wide text-muted">
                <th className="px-4 py-3 font-semibold">In the scraped examples</th>
                <th className="px-4 py-3 text-right font-semibold">Share</th>
                <th className="px-4 py-3 font-semibold">The app needs</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([what, share, need]) => (
                <tr key={share + need} className="border-b last:border-0">
                  <td className="px-4 py-3">{what}</td>
                  <td className="px-4 py-3 text-right font-semibold text-ink tabular">{share}</td>
                  <td className="px-4 py-3 text-muted">{need}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
```

- [ ] **Step 5: The data.** `site/components/data-pipeline.tsx`:

```tsx
import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

export function DataPipeline() {
  const steps = [
    {
      title: "Schemas and questions",
      text: `Claude Haiku wrote ${stat("schemas")} business table schemas, each with a real CSV, and ${stat("questions")} questions a person might ask of them.`,
    },
    {
      title: "Code answers",
      text: `Claude Sonnet wrote a Plotly answer for each of ${stat("targets_attempted")} training questions.`,
    },
    {
      title: "Kept only if it renders",
      text: `Every answer ran in the app's own sandbox against its CSV. ${stat("targets_kept")} rendered and were kept.`,
    },
    {
      title: "A frozen test set",
      text: `${stat("test_questions")} questions on ${stat("test_schemas")} schemas never seen in training, frozen before the first training run.`,
    },
    {
      title: "Two training sets",
      text: `lora-v1: ${stat("v1_train_rows")} rows, ${stat("v1_synthetic_rows")} from this pipeline and ${stat("v1_docs_rows")} docs examples rewritten to the app's contract. lora-v2: ${stat("v2_train_rows")}, adding analyst and planner examples distilled from Claude Opus 5.5.`,
    },
  ];
  return (
    <Section id="data" kicker="The data" title="Training data the app's own sandbox approved">
      <ol className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        {steps.map((step, index) => (
          <li key={step.title} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-pine tabular">{String(index + 1).padStart(2, "0")}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{step.title}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{step.text}</p>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-[13px] text-muted">
        The Claude API cost of the data: {stat("v1_data_cost", 2)} for lora-v1, {stat("v2_data_cost")} for lora-v2.
      </p>
    </Section>
  );
}
```

- [ ] **Step 6: The loss chart.** `site/components/loss-chart.tsx`:

```tsx
/* A validation-loss curve as an inline SVG: the page's own figure, drawn from
   data/loss.json, which tests/loss.test.mts checks against the training
   records. Not a model's chart. One series, so no legend: the caption names
   it. A 2 px line, 8 px markers with a surface ring, only the highest and
   lowest values labelled, a native tooltip per point, and the values again as
   a table for screen readers. */
export function LossChart({
  label,
  points,
  names,
  caption,
}: {
  label: string;
  points: number[];
  names: string[];
  caption: string;
}) {
  const width = 300;
  const height = 160;
  const pad = { left: 46, right: 14, top: 16, bottom: 22 };
  const max = Math.max(...points);
  const min = Math.min(...points);
  const x = (i: number) => pad.left + (i / (points.length - 1)) * (width - pad.left - pad.right);
  const y = (v: number) => pad.top + ((max - v) / (max - min || 1)) * (height - pad.top - pad.bottom);
  const path = points.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");

  return (
    <figure className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="font-display text-[15px] font-semibold text-ink">{label} · validation loss</span>
        <span className="text-[12px] text-muted">{caption}</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-3 w-full"
        role="img"
        aria-label={`${label} validation loss, from ${points[0]} to ${points[points.length - 1]}`}
      >
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={height - pad.bottom}
          y2={height - pad.bottom}
          stroke="var(--hairline)"
          strokeWidth={1}
        />
        <text x={pad.left - 8} y={y(max) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
          {max}
        </text>
        <text x={pad.left - 8} y={y(min) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
          {min}
        </text>
        <path d={path} fill="none" stroke="var(--pine)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {points.map((v, i) => (
          <g key={names[i]}>
            <circle cx={x(i)} cy={y(v)} r={4} fill="var(--pine)" stroke="var(--surface)" strokeWidth={2} />
            <circle cx={x(i)} cy={y(v)} r={11} fill="transparent">
              <title>{`${names[i]}: ${v}`}</title>
            </circle>
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>{label} validation loss</caption>
        <tbody>
          {points.map((v, i) => (
            <tr key={names[i]}>
              <th scope="row">{names[i]}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
```

- [ ] **Step 7: Training.** `site/components/training.tsx`:

```tsx
import loss from "@/data/loss.json";
import { LossChart } from "@/components/loss-chart";
import { stat } from "@/components/numbers";
import { Lede, Section } from "@/components/section";

export function Training() {
  const v1Names = loss.v1.points.map((_, i) => (i === 0 ? "before training" : `evaluation ${i}`));
  const v2Names = loss.v2.steps.map((step) => `step ${step.toLocaleString("en-US")}`);
  return (
    <Section id="training" kicker="Training" title="LoRA on one rented A100">
      <div className="grid gap-8 lg:grid-cols-[1fr_1.15fr] lg:gap-12">
        <div className="space-y-4">
          <Lede>
            LoRA adapters on Qwen3.5-9B, trained on one A100 80 GB on Runpod at {stat("gpu_rate")} an hour.
          </Lede>
          <Lede>
            lora-v1: {stat("v1_pod_time")} of pod time, validation loss {stat("v1_loss_start")} →{" "}
            {stat("v1_loss_end")}, {stat("v1_cloud_cost", 2)} of cloud time.
          </Lede>
          <Lede>
            lora-v2: {stat("v2_epochs")} epochs, {stat("v2_steps")} steps, {stat("v2_hours")} h, validation loss{" "}
            {stat("v2_loss_start")} → {stat("v2_loss_end")}, {stat("v2_cloud_cost")} of cloud time. The two runs score
            against different validation sets, so their curves do not compare.
          </Lede>
          <Lede>Each adapter is converted from PEFT to MLX and served at 4-bit on a Mac with mlx_lm, beside the app.</Lede>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <LossChart
            label={loss.v1.label}
            points={loss.v1.points}
            names={v1Names}
            caption={`before training, then ${loss.v1.points.length - 1} evaluations`}
          />
          <LossChart
            label={loss.v2.label}
            points={loss.v2.points}
            names={v2Names}
            caption={`${v2Names[0]} to ${v2Names[v2Names.length - 1]}`}
          />
        </div>
      </div>
    </Section>
  );
}
```

- [ ] **Step 8: Results.** `site/components/results.tsx`:

```tsx
import { Num } from "@/components/num";
import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

type Row = { measure: string; ids: [string | null, string, string] };

export function Results() {
  const groups: Array<{ test: string; rows: Row[] }> = [
    {
      test: `Frozen ${stat("test_questions")} questions, 4-bit on a Mac`,
      rows: [
        { measure: "Chart scripts that run", ids: ["base_render_mac", "v1_render_mac", "v2_render_mac"] },
        { measure: "The right kind of chart", ids: ["base_shape_mac", "v1_shape_mac", "v2_shape_mac"] },
      ],
    },
    {
      test: `Frozen ${stat("test_questions")} questions, full precision`,
      rows: [
        { measure: "Chart scripts that run", ids: ["base_render_pod", "v1_render_pod", "v2_render_pod"] },
        { measure: "The right kind of chart", ids: ["base_shape_pod", "v1_shape_pod", "v2_shape_pod"] },
      ],
    },
    {
      test: `${stat("plan_requests")} frozen dashboard requests`,
      rows: [
        { measure: "Plans that needed a retry", ids: [null, "plan_retry_v1", "plan_retry_v2"] },
        { measure: "Drawn charts that render", ids: [null, "plan_render_v1", "plan_render_v2"] },
        { measure: "Drawn as the planned kind", ids: [null, "plan_kind_v1", "plan_kind_v2"] },
      ],
    },
  ];
  return (
    <Section id="results" kicker="Results" title="Measured on questions it never saw">
      <div className="overflow-x-auto rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
        <table className="w-full min-w-[620px] text-left text-[14px]">
          <thead>
            <tr className="border-b text-[12px] uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-semibold">Test</th>
              <th className="px-4 py-3 font-semibold">Measure</th>
              <th className="px-4 py-3 text-right font-semibold">Base</th>
              <th className="px-4 py-3 text-right font-semibold">lora-v1</th>
              <th className="px-4 py-3 text-right font-semibold">lora-v2</th>
            </tr>
          </thead>
          <tbody>
            {groups.flatMap((group) =>
              group.rows.map((row, index) => (
                <tr
                  key={`${group.test} ${row.measure}`}
                  className={index === group.rows.length - 1 ? "border-b last:border-0" : ""}
                >
                  {index === 0 ? (
                    <th scope="rowgroup" rowSpan={group.rows.length} className="px-4 py-3 align-top font-semibold text-ink">
                      {group.test}
                    </th>
                  ) : null}
                  <td className="px-4 py-3">{row.measure}</td>
                  {row.ids.map((id, column) => (
                    <td
                      key={column}
                      className={`px-4 py-3 text-right tabular ${column === 2 ? "font-semibold text-ink" : ""}`}
                    >
                      {id ? <Num id={id} /> : <span className="text-muted">not run</span>}
                    </td>
                  ))}
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      <ul className="mt-4 space-y-1.5 text-[13px] leading-relaxed text-muted">
        <li>
          Base on the Mac runs with thinking off, its best setting. At full precision it ran with thinking on, so{" "}
          {stat("base_render_pod")} measures its essay, not its charts.
        </li>
        <li>lora-v1 against lora-v2 on the Mac, chart scripts that run: exact McNemar p = {stat("v1_v2_p")}.</li>
        <li>
          Dashboard requests: schemas kept out of training, and the first {stat("plan_drawn_per_dashboard")} charts of
          each dashboard drawn.
        </li>
        <li>Each number links to the file that recorded it.</li>
      </ul>
    </Section>
  );
}
```

- [ ] **Step 9: How it works.** `site/components/how-it-works.tsx`:

```tsx
import { stat } from "@/components/numbers";
import { Section } from "@/components/section";

export function HowItWorks() {
  const steps = [
    { name: "Analyst", text: "Reads a profile of every table, from its values alone, and proposes what to show." },
    { name: "Planner", text: "Writes every chart's plan in one call: kind, table, columns, aggregation and title." },
    {
      name: "Plan checks",
      text: `Test every column against the real tables. Problems go back in plain words, up to ${stat("plan_tries")} tries.`,
    },
    { name: "Chartist", text: "The fine-tuned model writes the Plotly code for each plan." },
    { name: "Sandbox", text: "Runs the code on the data. Code that fails goes back to the model." },
    {
      name: "Drawing check",
      text: `Lines that run back and forth and bars that stack raw rows go back too. A chart gets at most ${stat("max_repairs")} fixes.`,
    },
  ];
  return (
    <Section id="how" kicker="How the app works" title="Every chart is the model's own code">
      <ol className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        {steps.map((step, index) => (
          <li key={step.name} className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
            <p className="font-mono text-[11.5px] text-pine tabular">{String(index + 1).padStart(2, "0")}</p>
            <h3 className="mt-2 font-display text-[16px] font-semibold leading-snug">{step.name}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed">{step.text}</p>
          </li>
        ))}
      </ol>
      <p className="mt-4 rounded-[var(--r-card)] bg-pine-wash px-5 py-4 text-[14px] leading-relaxed text-ink">
        <strong>No hardcoded charts.</strong> A chart the model cannot draw after {stat("max_repairs")} fixes is reported
        as failed, never replaced by a template.
      </p>
      <p className="mt-3 text-[13px] text-muted">
        A single chart asked for in plain words takes the same path, with a detective to pick its table and a narrator to
        title it.
      </p>
    </Section>
  );
}
```

- [ ] **Step 10: Run it.** `site/components/run-it.tsx`. These are AGENTS.md's known-good commands; part 3 (setup and README) may change them, and this section changes with it.

```tsx
import { Lede, Section } from "@/components/section";
import { REPO_URL, fileUrl } from "@/lib/site";

const COMMANDS = [
  `git clone ${REPO_URL}.git`,
  `cd ${REPO_URL.split("/").pop()}`,
  "make setup",
  "make serve-model   # terminal 1: the model",
  "make up            # terminal 2: the app, on localhost:3000",
  "make smoke         # an end-to-end check",
].join("\n");

export function RunIt() {
  return (
    <Section id="run" kicker="Run it" title="Run it on your Mac">
      <div className="grid gap-6 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-4">
          <Lede>
            The model runs on the host with mlx_lm, which needs Apple Silicon; the app runs in Docker beside it. Your data
            and the model stay on your machine.
          </Lede>
          <Lede>
            The{" "}
            <a href={fileUrl("README.md")} className="text-pine underline underline-offset-2">
              README
            </a>{" "}
            has the details, and{" "}
            <a href={fileUrl("AGENTS.md")} className="text-pine underline underline-offset-2">
              AGENTS.md
            </a>{" "}
            the measured decisions behind them.
          </Lede>
        </div>
        <pre className="overflow-x-auto rounded-[var(--r-card)] bg-inverse p-5 font-mono text-[13px] leading-relaxed text-on-dark">
          <code>{COMMANDS}</code>
        </pre>
      </div>
    </Section>
  );
}
```

- [ ] **Step 11: Footer.** `site/components/footer.tsx`. Its data credits come from the dashboard files, so they follow Task 1's decisions.

```tsx
import { DASHBOARDS } from "@/components/dashboards";
import { AUTHOR, REPO_URL } from "@/lib/site";

const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";

export function Footer() {
  return (
    <footer className="mt-10 border-t">
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-10 text-[13px] leading-relaxed text-muted sm:px-8">
        <p>
          Built by{" "}
          <a href={AUTHOR.url} className={link}>
            {AUTHOR.handle}
          </a>
          . Base model: Qwen3.5-9B.{" "}
          <a href={REPO_URL} className={link}>
            The code is on GitHub
          </a>
          .
        </p>
        <ul className="space-y-1">
          {DASHBOARDS.map((dashboard) => (
            <li key={dashboard.name}>
              <span className="text-body">{dashboard.title}:</span>{" "}
              {[...new Set(dashboard.sources.map((source) => source.note))].join(" ")}{" "}
              {[...new Set(dashboard.sources.map((source) => source.licence))].join(", ")}.
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
```

- [ ] **Step 12: The whole page, in the spec's order.** `site/app/page.tsx`:

```tsx
import { Dashboards } from "@/components/dashboards";
import { DataPipeline } from "@/components/data-pipeline";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/how-it-works";
import { Journey } from "@/components/journey";
import { Problem } from "@/components/problem";
import { Results } from "@/components/results";
import { RunIt } from "@/components/run-it";
import { Training } from "@/components/training";

export default function Home() {
  return (
    <>
      <main>
        <Hero />
        <Dashboards />
        <Journey />
        <Problem />
        <DataPipeline />
        <Training />
        <Results />
        <HowItWorks />
        <RunIt />
      </main>
      <Footer />
    </>
  );
}
```

- [ ] **Step 13: Lint, test and build**

Run: `cd site && npm run lint && npm test && npm run build && grep -c "undefined\|NaN" out/index.html`
Expected: no lint errors; all tests pass; the build exports `/`; the grep prints `0`.

- [ ] **Step 14 (controller): Read the page in the browser,** at desktop width and with the `mobile` preset:
  - every section renders, and each number is the one in the spec;
  - the result numbers link to their files;
  - each journey commit opens on GitHub (with the owner signed in while the repository is private);
  - the loss charts show a tooltip on each point;
  - nothing scrolls sideways at phone width, except the results table inside its own box.

  Reset the viewport to `desktop` afterwards.

- [ ] **Step 15: Commit**

```bash
git add site/components site/app/page.tsx
git commit -m "feat(site): the story, from scraped docs to a measured adapter

Journey, problem, data, training, results, how it works and how to run
it, each a few sentences and one figure. Every number comes from
stats.json and the results link each one to its file. The loss curves
are the page's own SVG from the checked loss.json; the footer credits the
data from the dashboard files.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Deploy files, notes, and the final checks

**Files:**
- Create: `site/vercel.json`, `site/README.md`
- Modify: `AGENTS.md` (a short landing page section)

- [ ] **Step 1: Vercel config.** `site/vercel.json`. With the project's root directory set to `site`, `.` is `site/`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "nextjs",
  "ignoreCommand": "git diff --quiet HEAD^ HEAD -- ."
}
```

- [ ] **Step 2: `site/README.md`:**

````markdown
# PromptDash landing page

A static Next.js site (`output: "export"`) that tells how PromptDash's chartist was fine-tuned and shows three dashboards the app drew. Everything it shows is in `data/`; nothing is fetched from an API at run time.

## Run it

```bash
npm install
npm run dev     # http://localhost:3100
npm test        # the copies, every number, the loss curves, the milestones, the dashboards
npm run build   # the static site, in out/
```

## What the tests keep true

- `lib/dot-shapes.ts`, `lib/dot-draw.ts`, `lib/plot-theme.ts` and `lib/rich-text.ts` are byte-identical copies of byd-web's. Change byd-web's file, then run `npm run sync-lib`.
- Every number on the page is in `data/stats.json` with its source: a JSON path, an exact quote, or a sum. A number with no recorded source does not go on the page. Editing a quoted line in a README breaks the test on purpose: update the quote, or the number.
- `data/loss.json` matches the training records, and `data/journey.json` cites a commit for each milestone. If the history is rewritten, find each new hash by its subject.
- `data/dashboards/*.json` are the app's own output, unedited. Make them with `backend/scripts/fetch_showcase_data.py`, then `make showcase NAME=...` from the repository root. A dashboard that falls short is rebuilt from a rephrased prompt; its charts are never edited.

## Deploying on Vercel

The owner does this once:

1. Import the repository in Vercel.
2. Set the root directory to `site`. The framework is Next.js.
3. `vercel.json` skips the build for commits that do not touch `site/`.
4. Deploy from `main`. Until the repository is public, use preview deployments only.
````

- [ ] **Step 3: Notes for the next agent.** In `AGENTS.md`, add this section after "Frontend integration details":

```markdown
## Landing page (`site/`)
- A static Next.js export (`output: "export"`), deployed by Vercel with root directory `site`; `site/vercel.json` skips commits that do not touch `site/`. Previews only until the repository is public (part 2).
- Every number is in `site/data/stats.json` with its source (a JSON path, an exact quote or a sum), and `npm test` in `site/` reads each one back. Editing a quoted line in a README or here breaks that test on purpose.
- `site/lib/{dot-shapes,dot-draw,plot-theme,rich-text}.ts` are byte-identical copies of byd-web's. Change byd-web's, then run `npm run sync-lib`.
- The three dashboards are the app's own output: `backend/scripts/fetch_showcase_data.py` downloads the files into the gitignored `backend/uploads/showcase/`, then `SHOWCASE_PASSWORD=... make showcase NAME=airbnb|spotify|netflix` builds each one through the API. Charts are never edited; a dashboard that falls short is rebuilt from a rephrased prompt.
- `site/data/journey.json` cites commit hashes. A history rewrite changes them, and its test says so.
```

- [ ] **Step 4: Every check, from a clean state**

Run:

```bash
cd byd-web && npm test && npm run lint && npm run build && cd ..
cd backend && .venv/bin/python -m pytest -q tests && cd ..
cd site && npm test && npm run lint && npm run build && cd ..
```

Expected: everything passes. Report any failure with its output; do not hide it.

- [ ] **Step 5 (controller): The exported site, without a dev server.** Run `python3 -m http.server 3101 -d site/out` in the background, open http://localhost:3101 in the browser pane, and check:
  - the fonts and chunks load from the export;
  - the hero animates;
  - all three tabs draw their charts;
  - the GitHub and source links point at `https://github.com/tukka25/BYD/...`;
  - the page reads well with the `mobile` preset.

  Then use `read_network_requests` to confirm that, before scrolling, neither Plotly nor a dashboard chunk has loaded. Note the total transferred. Stop the server and reset the viewport.
- [ ] **Step 6 (controller): Design pass.** Run the `impeccable` skill's critique on the running page at desktop and phone widths. Fix what it finds within the spec, in byd-web's visual language, then repeat Step 4.
- [ ] **Step 7: Commit**

```bash
git add site/vercel.json site/README.md AGENTS.md
git commit -m "docs(site): how the landing page is built, checked and deployed

vercel.json skips commits that do not touch site/; the README says what
the tests keep true and how the owner sets up Vercel. AGENTS.md gets the
rules a later change has to keep.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8 (controller): Hand over to the owner.** Show screenshots of the page at desktop and phone widths, and of each dashboard. Then ask for the OK to push `feat/landing-page` and open a pull request. The owner creates the Vercel project, following `site/README.md`; the first deploy is a preview while the repository is private. Once that preview exists, open it in the browser pane and repeat Step 5's load check against it (what loads before scrolling, and the total transferred). That is the spec's performance check.

---

## After this plan

- **Part 2 (open source)** renames the repository: change `REPO_URL` in `site/lib/site.ts`. If it rewrites history, update the hashes in `site/data/journey.json`. If it edits a quoted README line, update `site/data/stats.json`. Add the licence to the footer.
- **Part 3 (setup and README)** may change the commands in `site/components/run-it.tsx`.

---

# Part B: the owner's redesign and the final review's fixes

Spec: "Revision 2" at the end of the spec. Ledger: the "FINAL REVIEW" and "OWNER REDESIGN REQUEST" entries. Global Constraints above still hold.

### Task B1: The final review's correctness fixes

**Files:** `byd-web/lib/plot-theme.ts` (+ `npm run sync-lib` in `site/`), `byd-web/tests/plot-theme.test.mts`, `backend/scripts/make_showcase.py`, `backend/tests/test_make_showcase.py`, `backend/scripts/fetch_showcase_data.py`, `site/README.md`.

- [ ] **Currency with a kept suffix (I1).** In the indicator branch, note whether a currency mark was removed: `const hadMark = isCurrencyMark(number.prefix) || isCurrencyMark(number.suffix);` before the two deletions, and change the last line to `if (currency && !number.prefix && (hadMark || !number.suffix)) number.prefix = currency;`. Add tests first (watch them fail): prefix `"$"` + suffix `"M"` with title `"Total MRR (USD)"` gives prefix `"$"` and suffix `"M"`; prefix `"$"` + suffix `"k"` with default `"GBP"` gives prefix `"£"`. Then `cd site && npm run sync-lib && npm test`.
- [ ] **Accepted prompts (I4).** In `SHOWCASES`, set each `prompt` to the prompt in its committed dashboard file (`site/data/dashboards/<name>.json`, field `prompt`) and add `"tries"` with that file's `build.prompts_tried`; make `--tries` default to the entry's `tries`. Add a test that each `SHOWCASES[name]["prompt"]` and `["tries"]` equal the committed file's `prompt` and `build.prompts_tried`.
- [ ] **No secret in an error (review minor).** `call()` must not copy a request body back: on an HTTP error, print the status and, for a JSON body with `detail` as a list, only each item's `loc` and `msg`; never `input`. Test with a fake 422 body holding `"input": "secret"`.
- [ ] **Size limit (review minor).** `write_dashboard` refuses `size >= limit` (the site refuses `>=`). Update its test.
- [ ] **Wording (L44).** `fetch_showcase_data.py` lines 14 and 62: say values are kept to Excel's precision (about 16 significant digits; long integer ids are written as text).
- [ ] **README deploy step (I2).** Replace step 4 with: "Set the project's production branch to `launch` (a branch that does not exist yet), so pushes to `main` build preview deployments only. Create `launch` from `main` when the repository is public (part 2)."
- [ ] Run byd-web, backend (`tests/test_make_showcase.py`, `tests/test_fetch_showcase_data.py`) and site tests; commit.

### Task B2: Dashboards as three cards with their own pages; no journey, no money

**Files:** `site/next.config.ts` (`trailingSlash: true`), new `site/app/dashboards/[name]/page.tsx`, new `site/components/dashboard-cards.tsx`, `site/components/dashboards.tsx`, `site/components/dashboard-view.tsx`, `site/app/page.tsx`, `site/components/hero.tsx`; delete `site/components/journey.tsx`, `site/data/journey.json`, `site/tests/journey.test.mts`, `site/components/dashboard-tabs.tsx`, `site/components/training.tsx`'s loss charts (`site/components/loss-chart.tsx`, `site/data/loss.json`, `site/tests/loss.test.mts`); `site/data/stats.json` (remove every money entry: `v1_data_cost`, `v2_data_cost`, `gpu_rate`, `v1_cloud_cost`, `v1_total_cost`, `v2_cloud_cost`, `total_cost`); `AGENTS.md` landing-page section (drop the journey line, mention the dashboard pages).

- Card titles: `airbnb` "Airbnb Dashboard", `shop` "Shop Dashboard", `netflix` "Netflix Dashboard" (a map in `site/lib/site.ts`, `DASHBOARD_TITLES`). Each card: the title, what the data is (source kinds, e.g. "Excel + CSV"), the prompt in quotes, and an "Open" affordance; the whole card links to `/dashboards/<name>/`. No chart counts or other numbers on the cards. The landing page loads no Plotly (no `LazyChart` there).
- The dashboard page: `generateStaticParams` returns the three names; `dynamicParams = false`. Top-left back link "← All dashboards" to `/#dashboards`; the title; the `DashboardView` grid with lazy charts; the frozen prompt box at the bottom (sticky only from `md` up: `md:sticky md:bottom-4`); provenance. Its `<title>` names the dashboard.
- Hero: remove the cost figure; keep the two improvement figures.
- Tests: `dashboard.test.mts` keeps validating the three files; add a check that every committed dashboard name has a title in `DASHBOARD_TITLES` and a key in `DASHBOARD_DATA`. Build must export `out/dashboards/{airbnb,shop,netflix}/index.html`.
- Copy is not rewritten here (Task B3), but no removed section or money may remain.
- Lint, test, build; commit.

### Task B3: The story, readable and without AI slop

**Files:** the section components (`problem.tsx`, `data-pipeline.tsx`, `training.tsx`, `how-it-works.tsx`, `results.tsx`, `run-it.tsx`, `footer.tsx`, `hero.tsx`, `dashboard-cards.tsx`, `section.tsx`), `site/app/globals.css` (type scale only), `site/data/stats.json` only to remove entries no section uses any more.

- Load and follow the skills `no-ai-slop`, `antislop`, `antislop-copywriting`, `antislop-ui`, `antislop-layoutmobile` (installed in `~/.claude/skills/`), within byd-web's visual language (`byd-web/DESIGN.md`).
- The story, in order: the problem (a capable base model that writes essays; docs scraped from plotly.com that taught the wrong habits), the data (the crawl; Claude Haiku writing table schemas and questions; Claude Sonnet writing code answers, kept only if they ran in the app's own sandbox; Claude Opus distilling the analyst and planner; a frozen test set the model never saw; lora-v2 as one adapter for three jobs), training (LoRA on a rented A100 on Runpod, converted to MLX, served 4-bit on a Mac), the harness (the analyst, the planner and its tools by name, the checks against the real tables, the chartist, the sandbox, the drawing check and the repairs; how prompts stay short: a short facts note instead of whole tables, a profile from a sample, drafts referred to by number), the results (one short table, base with thinking off vs lora-v2 at 4-bit on a Mac, plus the dashboard-planning results; numbers only from `stats.json` via `<Num>`), run it, footer.
- No money and no figures in the story text; facts must stay true to `AGENTS.md`, `chartist-finetune/README.md`, `chartist-finetune/cloud/README.md` and `chartist-finetune/export_v2.py`.
- Readability: body text at least 17-18 px with generous line height, in `--ink` rather than `--body`; captions no smaller than 14 px; line length about 65-75 characters.
- Footer: each source credited once (no repeated Airbnb note; capitalised licence lines).
- Hero figures never wrap mid-figure at 1024 px.
- Lint, test, build; check at desktop and 375 px (controller); commit.

### Task B4: Image cards, each with a preview of its dashboard

The owner asked twice:
- "for the cards, show like kind of a sneak peek photo of the graphs under it to know";
- then, with a screenshot of Kokonut UI's "carousel-cards": "show the cards this way ... it doesn't has to be carousel just the three there layout look something similar to this."

The reference shows three tall image cards with rounded corners. Each has a small label chip at the top left of the image and a round icon button at the top right. The title and a one-line subtitle sit under the image, not inside a box. The middle card is larger and sits higher; the side cards are a little smaller, lower, and tilted outward by a degree or two.

Build that look natively, in the site's own components and tokens. Do not run `npx shadcn` or install Kokonut UI or any other package. The site has no shadcn setup, and its init would rewrite `globals.css` and add a motion library to a page that loads nothing heavy. There is no carousel: no counter, no arrows, no autoplay.

The dashboard pages themselves are unchanged. They still draw live Plotly charts, and they never show an image standing in for a chart.

**Files:**
- Create:
  - `site/scripts/previews.mjs`, the capture script;
  - `site/public/previews/{airbnb,shop,netflix}.webp`, generated and committed;
  - `site/data/previews.json`, the record of what was captured;
  - `site/tests/previews.test.mts`.
- Modify:
  - `site/components/dashboard-cards.tsx`, the card;
  - `site/components/dashboard-view.tsx`, data attributes only, no visual change;
  - `site/next.config.ts`, `images: { unoptimized: true }` if you use `next/image`;
  - `site/package.json`, script `"previews": "node scripts/previews.mjs"`;
  - `site/README.md`;
  - `AGENTS.md`, one bullet in "Landing page (`site/`)".

**1. The capture script (`npm run previews`)**
- **Built-ins only.** Use Node 24 built-ins: global `fetch` and `WebSocket`, `node:child_process`, `node:http`, `node:crypto`, `node:fs`. No npm dependency and no download.
- **Chrome.** Use the `CHROME` environment variable, or else `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. If neither exists, fail with an error that names both.
- **Launch.**
  - Give Chrome a fresh temporary `--user-data-dir`, and remove it afterwards. Without one, a running Chrome swallows the launch.
  - Pass `--headless=new`, a remote-debugging port, `--no-first-run`, `--no-default-browser-check` and `--hide-scrollbars`.
  - Drive it over the DevTools protocol.
- **Server.** Serve `site/out/` from the script itself, on `127.0.0.1` with an ephemeral port (port 0).
  - `/x/` resolves to `/x/index.html`.
  - Send content types for html, js, css, json, woff2, webp, svg and png.
  - Serve no path outside `out/`, and never use :3100 or :3101.
- **Stale build.** Refuse to run when `out/` is missing, or is older than the newest file under `site/app`, `site/components`, `site/lib` or `site/data/dashboards`. Tell the user to run `npm run build` first.
- **Each dashboard.** Take each `site/data/dashboards/*.json`, sorted by name, and open `/dashboards/<name>/`.
  - Set the viewport 960 CSS px wide (the 12-column grid applies from 768 px) at device scale factor 1. Then make it taller than the whole page: its `scrollHeight` plus 200 px. At a normal height the sticky prompt box floats over the charts, and charts outside the 600 px observer margin never draw.
  - Wait for `document.fonts.ready`. Then wait until the page holds `build.charts_drawn` elements matching `.js-plotly-plot`, each with a `.main-svg`, and no chart shows a failure message.
  - Time out after 60 s per dashboard, with an error that names it.
- **The crop.** Use one rule for all three. If one image looks wrong, change the rule, never one dashboard.
  - Take the grid's full width, from the top of its first block that is not a note, at an aspect of 4:5 (height = width × 5/4).
  - Cut at the grid's bottom if the grid is shorter.
  - Find the grid and its blocks through data attributes added to `dashboard-view.tsx` (for example `data-preview-grid` and `data-block-kind`), not through class names.
- **The capture.** Call `Page.captureScreenshot` with `format: "webp"`, quality 80, `captureBeyondViewport: true`, and a `clip` whose `scale` makes the output 640 px wide (about twice the card's image). If this Chrome refuses webp, fail with a message. Never switch formats silently.
- **Output.** Write `site/public/previews/<name>.webp`. Then write `site/data/previews.json`:
  `{ "made_by": "scripts/previews.mjs", "viewport_width": 960, "crop": "<the rule in words>", "dashboards": { "<name>": { "file": "/previews/<name>.webp", "width": 640, "height": <px>, "sha256": "<hex sha256 of the dashboard JSON file's bytes>" } } }`.
- **Exit.** Exit non-zero on any failure. Always stop Chrome and the server and remove the temporary profile, including on failure.

**2. The card (`dashboard-cards.tsx`)**
- **One link per card.** It is named by its h3 (`aria-labelledby`, as now), and every part inside it is decorative or text.
- **The image tile.**
  - The preview fills a tall tile: aspect 4:5 from `md` up, and 4:3 below `md` with `object-fit: cover; object-position: top`.
  - Give the tile the `--r-panel` radius, a hairline ring, the `--lift-2` shadow, and the sunken surface behind it while it loads.
  - The image takes its own `width` and `height` from `data/previews.json`, with `loading="lazy"`, `decoding="async"` and `alt=""`.
- **On the tile.**
  - At the top left, a chip with the source kinds (`sourceKinds(dashboard)`: "Excel + CSV", "Postgres", "CSV"), legible over the image: a surface-coloured pill with a soft shadow.
  - At the top right, a round surface-coloured chip with an arrow-up-right glyph, as an inline SVG or added to `components/icons.tsx`. It is `aria-hidden` and is not a button.
  - No heart, no rating, no price, no counts.
- **Under the tile, not boxed.**
  - The title as the h3.
  - The prompt in quotes, clamped to two lines.
  - "Open the dashboard" with the arrow, as now.
- **The row from `md` up.**
  - Three cards in a row. The middle card is larger and sits higher.
  - The side cards are a little smaller and lower, tilted outward by about 2 degrees: left negative, right positive.
  - Hover and keyboard focus straighten and lift a card.
  - Transitions animate `transform` only, at no more than 200 ms. Under `prefers-reduced-motion: reduce` there are no transitions. The resting tilt may stay.
  - Keep the cards inside the content width, with no horizontal overflow at 768, 1024 and 1440 px.
- **Below `md`.** One column, no tilt, no scale, all three the same size, and no horizontal scroll at 375 px.
- **Keep the order.** The dashboard order stays as `DASHBOARDS` has it, so the shop card is in the middle.
- **Skills and design.** Follow `antislop-ui`, `antislop-layoutmobile` and `byd-web/DESIGN.md`. Keep `DashboardCards` a server component.

**3. What must stay true**
- The landing page loads no Plotly: no chunk referenced by `site/out/index.html` contains "plotly".
- The dashboard pages draw live charts; nothing there is an image of a chart.
- These files are not touched: `site/lib/{dot-shapes,dot-draw,plot-theme,rich-text}.ts` and `site/data/dashboards/*.json`.
- No new dependency.

**4. The test (`tests/previews.test.mts`)**
- For every `site/data/dashboards/*.json`, `data/previews.json` has an entry whose `sha256` equals the sha256 of the file's current bytes. A mismatch fails with "run npm run build && npm run previews".
- The image exists and is under 150 KB.
- Its WebP header's width and height equal the entry's. Parse the RIFF container's `VP8 `, `VP8L` and `VP8X` chunks.
- No entry names a dashboard that does not exist.

**5. Docs**
- `site/README.md` says:
  - what the previews are;
  - how to make them: `npm run build && npm run previews` (Google Chrome, or `CHROME=<path>`);
  - that they must be captured again after a dashboard changes, or after a change to how dashboards are drawn. The test catches only the first.
- `AGENTS.md`, "Landing page (`site/`)": one bullet saying the same in a line.

**6. Order**
1. Make the code changes.
2. Run `npm run build`, then `npm run previews`.
3. Look at the three images (Read shows them). If one is mostly empty, adjust the rule.
4. Run `npm run build` again so the images are in `out/`.
5. Run `npm run lint && npm test`.
6. Commit with the images.

### Task B5: The page as a first-person story, with the results back

The owner's message, condensed but faithful:
- **Hero line.** It should be "like: A 9B model fine-tuned to generate full dashboards and graphs from a prompt, your data never leaves your device", as a hook.
- **Hero numbers.** "the cards of from 69% to 94% no one will understand it ... put better information in a high level way for the reader to be able to understand."
- **Dashboards intro.** Replace the current paragraph with "something like: The dashboards (below) were generated by PromptDash on first shot, from the planning to the generation."
- **The problem section.** "Out of the box, the model wrote essays" is "too AI slop", so remove it. "write it as a blog like you are telling a story":
  - **Problem:** analysing classified data with cloud-hosted LLMs (Claude, GPT, ...) is dangerous; you can leak secret data. "so i was thinking what if we used small model to make those analysis and then the model was very inefficient": show KPI cards with the base model's results.
  - **Then:** "i decided to finetune Qwen (specs) in Plotly and put link to their main website, i used LoRA with PEFT, ..etc mlx (mention the methodology) and the performance was great and i made two versions v1 and v2, and the results are below": the results table.
  - **"1. How the data was gathered":** the scraping and the distillation, then the table of the agents' personas and the model used to generate their data.
  - **"2. Training":** minimal text, to the point. "i used runpod", with a link to their website.
  - **"3. Harness":** the harness, the tool calling and the steps.
  - **"Run it on your Mac":** keep it.

**Files you own:**
`site/components/{hero,dashboards,problem,results,data-pipeline,training,how-it-works,run-it,section}.tsx`, `site/app/page.tsx`, `site/app/globals.css` (type and layout only), `site/data/stats.json`, `site/tests/stats.test.mts`. You may add new components, for example a KPI card.

**Do not touch:**
- `footer.tsx`, `lib/site.ts`, `icons.tsx`, `dashboard-cards.tsx`, `dashboard-view.tsx`, `next.config.ts`, `package.json`, `site/README.md`, `AGENTS.md`, the root `README.md`. Other tasks own them.
- `site/lib/{dot-shapes,dot-draw,plot-theme,rich-text}.ts` and `site/data/dashboards/*.json`.
- If AGENTS.md needs a change, write it in your report instead.

**Page order:** hero, the three dashboards, the problem, fine-tuning and results, 1. How the data was gathered, 2. Training, 3. Harness, Run it on your Mac, then the footer (which you leave as it is).

**What each part must say**
1. **Hero.**
   - The h1 stays "PromptDash".
   - The subtitle is the owner's hook, close to their words, in two sentences: a 9B model fine-tuned to build full dashboards and charts from one prompt, and your data never leaves your device.
   - Replace the two "69% → 94%" cards with cards a cold reader understands. Each says, in plain words, what was measured, on what, and the before and after. "Before" is the base model with no fine-tuning; "after" is lora-v2.
   - Keep the two buttons. Every number comes through `<Num>`/`stat()`.
2. **Dashboards intro.** One or two sentences, true of all three: each came out of one run of PromptDash, from the plan to every chart, with nothing edited by hand.
   - Never say "first shot", "first try" or "first prompt". The prompts tried were airbnb 4, shop 1 and netflix 3, and each dashboard page states which.
   - The cards are restyled by another task; leave `dashboard-cards.tsx` alone.
3. **The problem**, first person and blog-like.
   - Analysing sensitive or classified data with a cloud-hosted model such as Claude or GPT means sending that data off your machine to someone else's servers. State the risk as data leaving the machine; never claim a named vendor leaks.
   - So: could a small model that runs locally do the analysis? Out of the box it could not. Show KPI cards for the base model, each labelled with its condition:
     - **Thinking on** (its default), full precision on a GPU: chart scripts that ran, and charts of the right kind. Re-add `base_render_pod` and `base_shape_pod` from `chartist-finetune/cloud/eval_report.json`, `['base','render_rate']` and `['base','right_shape_rate']`.
     - **Thinking off**, 4-bit on a Mac: `base_render_mac` and `base_shape_mac`.
   - Do not imply the fine-tune made the whole jump from thinking-on. Most of it was the reasoning essay (AGENTS.md: "Most of '7.7% -> 91.3%' is the reasoning essay, not the fine-tune; what the fine-tune bought is choosing the right chart").
   - Remove the old essay paragraph and the scraped-habits paragraph.
4. **Fine-tuning and the results.**
   - I fine-tuned Qwen3.5-9B, linked to its model page (`https://huggingface.co/Qwen/Qwen3.5-9B`, the id the repo uses), to write Plotly code, linked to `https://plotly.com/python/`.
   - Take specs only from repo files or that model card, and say which.
   - The method in plain words: LoRA adapters trained with Hugging Face PEFT on a rented GPU, converted to MLX, and run 4-bit on a Mac with mlx_lm.
   - Two versions. lora-v1 writes chart code. lora-v2 is one adapter for three jobs.
   - Then the results table (base, lora-v1, lora-v2 on the 300 frozen chart questions; lora-v1 and lora-v2 on the 120 frozen dashboard requests), with plain row labels and its notes.
5. **1. How the data was gathered.**
   - The first data was a Scrapy crawl of the Plotly docs (plotly.com/python). Say what was wrong with it in one or two plain sentences.
   - Then the distillation with Claude:
     - Haiku wrote table schemas and questions.
     - Sonnet wrote chart-code answers, kept only if they ran against their CSV in a sandbox that mirrors the app's and passed its checks.
     - Opus wrote the analyst's and planner's examples.
     - Held-out test sets never enter training.
   - Then a table of the personas: the role (chartist, analyst, planner), what it reads, what it writes, and which Claude model wrote its training examples.
6. **2. Training.** A few short sentences.
   - Training on the Mac ran out of memory.
   - LoRA with PEFT on one A100 rented on Runpod, linked to `https://www.runpod.io`.
   - The adapter is converted to MLX and served 4-bit on the Mac.
   - Keep a compact pipeline line if it helps. No money anywhere.
7. **3. Harness.** High level:
   - the steps from profile to drawn chart;
   - tool calling, with the tools by name and their modes. The default explore step holds `find_columns`, `inspect_column`, `relationship` and `preview`. The optional checking turn holds `row_grain` and `preview_chart`;
   - the plan checks, the sandbox, the drawing check, and at most two repairs;
   - how prompts stay short.
   - Tighter than now.
8. **Run it on your Mac.** Keep it, including the line that the optional Compare models page sends the question to Claude.

**Rules**
- **Voice.** First person ("I"), like a short blog post, in short paragraphs. Load and follow `no-ai-slop`, `antislop`, `antislop-copywriting`, `antislop-ui` and `antislop-layoutmobile` (Skill tool, or `~/.claude/skills/<name>/SKILL.md`). Run no-ai-slop's detect pass on the final copy and fix what it flags.
- **Numbers.** Numbers are back at the owner's request, as KPI cards and the results table only, and every one comes through `stats.json` with its source; the stats test reads each one back. Prose stays light on figures. No money, no costs, no prices.
- **Facts.**
  - Reuse the claim-to-source list in `/Users/atukka/Desktop/BYD/.superpowers/sdd/2026-11-25-promptdash-landing-page/task-B3-report.md` (in the main checkout) rather than deriving facts again.
  - Every new claim must be supported by `AGENTS.md`, `chartist-finetune/README.md`, `chartist-finetune/cloud/README.md`, `chartist-finetune/export_v2.py` or the code.
  - Check that every external link resolves (`curl -sIL -o /dev/null -w '%{http_code}'`).
- **Readability**, as now: `BODY` (17/18px, `--ink`), `CAPTION` at least 14px, `MEASURE` (42ch). No horizontal scroll at 375px.
- **Plotly.** The landing page loads no Plotly: no chunk that `out/index.html` references contains "plotly".

**Worktree setup** (you run in an isolated git worktree):
1. Print `git rev-parse --abbrev-ref HEAD` and `git rev-parse HEAD`.
2. Run `cp -cR /Users/atukka/Desktop/BYD/site/node_modules site/node_modules`, an APFS clone with no download.
3. If `npm run lint` cannot run, report BLOCKED. Never run `npm install`.
4. Build and serve only inside your worktree, on ephemeral ports. Never use :3100 or :3101.

**Verify:** `npm run lint && npm test && npm run build` in your worktree's `site/`. Measure line lengths and sideways overflow at 375, 768, 1024 and 1440px in headless Chrome (`/Applications/Google Chrome.app`), and look at your screenshots. Commit on your worktree branch, with every message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Task B6: The footer, redesigned

The owner: "the footer design it better but linkedin and github links and the repo link also at the end with the same design you made all the way up. and put the data links in, remove the sentences like those:" and then they quote the current credit lines:
- "Netflix Movies and TV Shows by Shivam Bansal on Kaggle, as mirrored by TidyTuesday (2021-04-20). CC0 1.0."
- "Seeded by backend/scripts/make_relational_demo.py: four tables, joined by their declared keys. Synthetic, made for this project."
- "Inside Airbnb, Edinburgh, snapshot 2026-09-19. CC BY 4.0."

**Files you own:** `site/components/footer.tsx`, `site/lib/site.ts`, and optionally a new `site/components/social-icons.tsx`.
**Do not touch:**
- `site/components/icons.tsx`: another task adds an arrow there. You may import `GitHubMark` from it.
- Every other component, `app/`, `data/`, `tests/` (except a new test file of your own), `AGENTS.md`, and the two READMEs.
- `dashboard-view.tsx`: the dashboard pages' credits get the same treatment later, in another task.

**What the footer holds**
- **Links**, with icons:
  - the GitHub profile (`AUTHOR.url` in `site.ts`, `https://github.com/tukka25`);
  - LinkedIn, from a new `LINKEDIN_URL` export in `site.ts`, empty for now. The link renders only when it is set. Never ship a placeholder or a guessed URL;
  - the repository (`REPO_URL`).
- **Data credits as links only.** Each dataset's name links to its source page. Drop the sentences above, and the snapshot and mirror details.
  - Inside Airbnb is CC BY 4.0, which requires attribution and a licence link. Keep the licence's short name, linked, beside the Airbnb link: no sentence, one short tag.
  - The Netflix data is CC0, so it needs only its link.
  - The shop data is synthetic, made for this project. A short tag such as "synthetic", linked to its generating script in the repository, is enough.
  - Derive names and URLs from the dashboard files' `sources` (`name`, `url`, `licence`, `licence_url`, `note`) and from what the current footer already computes. Do not hand-write per-dataset strings the data already holds.
- **Anything else the current footer says** that is still true and short (the model and adapter credit, the build date) may stay if it fits the new design. Cut sentences.

**Design**
- Same design language as the rest of the page: byd-web's tokens (`site/app/globals.css`), the card and pill shapes, the pine accent, and text at 14px or more in `--ink` and `--muted`.
- Read `/Users/atukka/Desktop/BYD/byd-web/DESIGN.md`, and load the `antislop`, `antislop-ui` and `antislop-layoutmobile` skills (Skill tool, or `~/.claude/skills/<name>/SKILL.md`).
- Every link is a real `<a>` with a visible label or an `aria-label`. External links get `rel="noopener noreferrer"` when they open a new tab. Tap targets are at least 44px on phones.
- No horizontal scroll at 375px.

**Worktree setup** (you run in an isolated git worktree):
1. Print `git rev-parse --abbrev-ref HEAD` and `git rev-parse HEAD`.
2. Run `cp -cR /Users/atukka/Desktop/BYD/site/node_modules site/node_modules`, an APFS clone with no download.
3. If `npm run lint` cannot run, report BLOCKED. Never run `npm install`.
4. Build and serve only inside your worktree, on ephemeral ports. Never use :3100 or :3101.

**Verify:** `npm run lint && npm test && npm run build` in your worktree's `site/`. Screenshot the footer in headless Chrome (`/Applications/Google Chrome.app`) at 375 and 1280px, and look at it. Commit on your worktree branch, with every message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Task B7: The root README, readable and to the point

The owner: "make sure the read me is nicely designed and to the point so it can be read easily without jargon."

**File you own:** `/README.md` at the repository root. Do not edit anything else. In particular, leave `chartist-finetune/README.md` alone: the site's stats test quotes it.

**What it holds**, in this order and short:
1. **The name and a one-line hook.**
   - The app is PromptDash, and the repository is still named BYD. Make no claim about a rename.
   - The hook matches the landing page's: a 9B model fine-tuned to build full dashboards and charts from one prompt, and your data stays on your machine.
2. **What it does**, in three or four plain bullets: ask in plain words, with files or a Postgres/MySQL database as the data, and get a dashboard planned and drawn by the local model.
3. **How it works**, in a few sentences:
   - one fine-tuned adapter on Qwen3.5-9B does three jobs (analyst, planner, chartist);
   - code checks every plan against the real tables, and every chart is drawn by the model's own code, with at most two fixes;
   - link to `AGENTS.md` for the measured decisions and to `chartist-finetune/README.md` for the fine-tune.
4. **Quick start on a Mac**, with commands taken from the root `Makefile` (`make help` lists them): what you need (Apple Silicon, Docker, and whatever `make doctor` checks), then `make setup`, `make serve-model` in terminal 1, `make up` in terminal 2, and `make smoke`.
   - Say where the app opens (read `docker-compose.yml` and the Makefile for the port).
   - Say how the base model and the adapter get onto the machine. `chartist-finetune/README.md` has the download command.
   - Mention `make secrets`: the committed defaults are placeholders.
5. **Privacy, in one short paragraph.** Dashboards are built by the local model. The optional Compare models page sends the question and a data sample to Claude. Check what it sends in `backend/app/api/v1/endpoints/comparison.py` and `backend/app/services/claude_chartist.py`, and describe it exactly.
6. **What's in the repository**, a short table: `backend/`, `byd-web/`, `chartist-finetune/`, `web-crawler/`, `site/`, `langchain-archeticture/`, each with one plain line.
7. **Further reading:** `AGENTS.md`, `chartist-finetune/README.md`, `chartist-finetune/cloud/README.md`, `site/README.md`.

**Rules**
- Plain words with no jargon. Where a technical term is needed (LoRA, MLX), say what it is in a few words the first time.
- Load and follow `no-ai-slop` and `antislop-copywriting` (Skill tool, or `~/.claude/skills/<name>/SKILL.md`), and run no-ai-slop's detect pass on the final text.
- Nicely designed in plain GitHub Markdown: short sections, one table, fenced shell blocks, no badge wall, no emoji headings, no HTML tricks that GitHub strips.
- **Facts** come from `Makefile`, `docker-compose.yml`, `backend/.env.example` (never read `.env`), `AGENTS.md`, `chartist-finetune/README.md` and the code.
  - No money, no costs, no licence claim (the licence comes in a later part), no rename claim.
  - Any number you include must appear in those files verbatim.
- **Links.** Every relative link must point to a file that exists. Check each one.

**Worktree setup** (you run in an isolated git worktree): first print `git rev-parse --abbrev-ref HEAD` and `git rev-parse HEAD`. No build is needed. Commit on your worktree branch, with the message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

