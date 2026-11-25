# PromptDash landing page

A static Next.js site (`output: "export"`) that tells how PromptDash's chartist was fine-tuned and shows three dashboards the app drew. Everything it shows is in `data/`; nothing is fetched from an API at run time.

## Run it

```bash
npm install
npm run dev       # http://localhost:3100
npm test          # the copies, every number, the dashboards, the previews
npm run build     # the static site, in out/
npm run previews  # the cards' pictures, taken from out/ (see below)
```

## The previews on the cards

Each dashboard card on the landing page shows a picture of its dashboard's first charts: `public/previews/<name>.webp`, listed with its size in `data/previews.json`. They are the only pictures of charts on the site. The landing page loads no Plotly, and the dashboard pages still draw every chart live.

`scripts/previews.mjs` takes them from the built pages. It serves `out/` itself, opens each dashboard in headless Google Chrome at 960 px, waits until every chart is drawn, and crops the grid from its first chart at 4:5. It uses Node's built-ins and the Chrome already installed, and downloads nothing.

```bash
npm run build && npm run previews   # Chrome at its standard macOS path, or CHROME=<path to a Chrome binary>
npm run build                       # again, so out/ carries the new pictures
```

Take them again whenever a dashboard changes, and whenever the way dashboards are drawn changes (the grid, the chart theme, the fonts). `tests/previews.test.mts` catches only the first: it fails when a file in `data/dashboards/` no longer matches the sha256 recorded with its picture.

## What the tests keep true

- `lib/dot-shapes.ts`, `lib/dot-draw.ts`, `lib/plot-theme.ts` and `lib/rich-text.ts` are byte-identical copies of byd-web's. Change byd-web's file, then run `npm run sync-lib`.
- Every number on the page is in `data/stats.json` with its source: a JSON path, an exact quote, or a sum. A number with no recorded source does not go on the page. Editing a quoted line in a README breaks the test on purpose: update the quote, or the number.
- The story itself carries no figures and no money. The only numbers are the hero's two before-and-after results and the results table, and a test fails if `data/stats.json` holds an entry no component shows.
- `data/dashboards/*.json` are the app's own output, unedited. Make them with `backend/scripts/fetch_showcase_data.py`, then `make showcase NAME=...` from the repository root. A dashboard that falls short is rebuilt from a rephrased prompt; its charts are never edited.

## Deploying on Vercel

The owner does this once:

1. Import the repository in Vercel.
2. Set the root directory to `site`. The framework is Next.js.
3. `vercel.json` skips the build for commits that do not touch `site/`.
4. Set the project's production branch to `launch` (a branch that does not exist yet), so pushes to `main` build preview deployments only. Create `launch` from `main` when the repository is public (part 2).
