# PromptDash landing page

A static Next.js site (`output: "export"`) that tells how PromptDash's chartist was fine-tuned and shows three dashboards the app drew. Everything it shows is in `data/`; nothing is fetched from an API at run time.

## Run it

```bash
npm install
npm run dev     # http://localhost:3100
npm test        # the copies, every number, the dashboards
npm run build   # the static site, in out/
```

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
