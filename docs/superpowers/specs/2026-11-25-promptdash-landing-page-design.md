# PromptDash landing page — design

Date: 2026-11-25. Agreed in conversation, section by section; this file records it.

## Goal

A public landing page for PromptDash, hosted on Vercel, that:

- tells the project's story for a technical reader: how the training data was made, how the LoRA adapter was trained, and what it changed;
- shows three real dashboards the app drew, each with the prompt that drew it;
- quotes only measured numbers, each traceable to the file that recorded it;
- links to the GitHub repository.

## Scope

This is part 1 of 3. Parts 2 and 3 get their own designs.

1. **Landing page** (this document).
2. **Open source:** remove old and unneeded files, scan the whole git history for secrets, choose a licence, rename the repository to `promptdash`, make it public.
3. **Setup and README:** a setup that a person or an agent can follow end to end, and a README with the dot animation as an animated SVG.

The repository is private until part 2, so its links would not open for visitors. Until then the page is deployed as Vercel previews only. The public launch waits for part 2, when the repository is renamed and made public; until the rename the page links to `github.com/tukka25/BYD`.

The work happens on the branch `feat/landing-page`. `main` is what Vercel deploys to production, so the page reaches `main` by merge.

## Decisions

| Question | Decision |
|---|---|
| Name | PromptDash |
| Where the page lives | `site/` on `main`, a separate Next.js app. No separate branch. |
| Hosting | A Vercel project with root directory `site`. Commits that do not touch `site/` do not redeploy. |
| Dashboards on the page | Live Plotly charts drawn from exported data, not screenshots |
| The three datasets | Airbnb Edinburgh (Excel and CSV files), Spotify songs (Postgres), the Netflix catalogue (one CSV) |
| Credit | @tukka25 on GitHub |

## Architecture

### `site/`

- Next.js (the version byd-web uses), `output: "export"`, TypeScript, Tailwind. No server and no API calls at run time: everything the page shows is in the build.
- Visual language: `byd-web/DESIGN.md`. The same colour tokens, the same three typefaces served from the site's own origin through `next/font`, the same motion rules, the same chart re-theme.
- Four pieces of code come from byd-web as byte-identical copies, and a test fails if a copy differs from its original. Two of them are first moved out of components into `lib/`, with no change in behaviour and the app using the moved code:
  - `byd-web/lib/dot-shapes.ts`: the geometry of the dot animation, as it is.
  - `byd-web/lib/dot-draw.ts` (new): the draw loop that today sits inside `components/build-loader.tsx`, which draws one frame of dots onto a canvas. `BuildLoader` keeps its label and timer and calls it, and the hero calls the copy, so the hero is the same animation, not a lookalike.
  - `byd-web/lib/plot-theme.ts` (new): the chart re-theme from `components/plot.tsx` (`themed` and its helpers). Its one outside input, the default currency that `plot.tsx` reads from `NEXT_PUBLIC_DEFAULT_CURRENCY`, becomes a parameter.
  - `byd-web/lib/rich-text.ts`: the app's HTML sanitiser, as it is, for the text block below.

### Data the page reads (`site/data/`)

- **`stats.json`:** every number on the page. Each entry has an id, the value as displayed, a label, the file it comes from, and how the test confirms it:
  - `json`: a file and a key path. The test reads the value again and compares it.
  - `quote`: the exact text in a document (for example `$8.42` in `chartist-finetune/cloud/README.md`). The test checks that it appears there verbatim.
  - `sum`: the ids it adds up. The test recomputes the total.
  - **Rule: a number with no recorded source does not go on the page.**
- **`dashboards/airbnb.json`, `spotify.json`, `netflix.json`:** one file per dashboard:
  - `prompt`: exactly as sent.
  - `sources`: name, kind (file or database), rows, URL, licence, note.
  - `blocks`: kind, title, Plotly figure or `text_body`, grid `x`/`y`/`w`/`h`, chart type, exactly as the app saved them. Every build adds one text block: an introduction that the app's code (not the model) writes as HTML from the data profile. The page renders it through the sanitiser copy, as the app does.
  - `currency`: the currency the source states for its money columns (Inside Airbnb gives prices in local currency, GBP for Edinburgh), passed to the re-theme the way the app's `NEXT_PUBLIC_DEFAULT_CURRENCY` is. Empty when the source states none: a currency is never invented.
  - `build`: charts planned, drawn and skipped, seconds, prompts tried.
  - `model`, `app_commit` and `generated_at`.

## The page, top to bottom

Each section is a few technical sentences and one figure, table or diagram.

1. **Hero.** Left: the name, one line on what PromptDash is (ask for a dashboard in plain words; a 9B model fine-tuned for Plotly writes every chart, on your own machine), a GitHub button and a link down to the dashboards. Three headline numbers: chart scripts that run and charts of the right kind, each as the base model's share → lora-v2's (94% and 82%), both on the frozen 300 at 4-bit on a Mac; and about $35 to train. Right: the dot animation, morphing through all 14 chart shapes without end.
2. **Three dashboards.** Each one live, styled like the app's view mode, with its prompt in a fixed box below it. Then the data source and its licence, and "drawn by lora-v2, unedited", with the date.
3. **Journey.** A strip of dated milestones read from `git log`, each citing its commit: the first commit (2026-03-07), the training data, lora-v1 (2026-11-20), lora-v2 and dashboards planned by the model (2026-11-21, `a91d276`), no hardcoded charts (2026-11-23, `7deeaa3`), the bar drawing check (2026-11-25, `2d7af93`).
4. **The problem.**
   - Out of the box, Qwen3.5-9B answers with a reasoning essay, and 7.7% of its chart scripts run (frozen 300, full precision).
   - With thinking off, on the same 300 questions at 4-bit on a Mac, more of its scripts run, but few draw the right kind of chart: the base row of the results table.
   - The scraped Plotly docs taught the opposite of what the app needs. Table: 0% end with `print(fig.to_json())`, 96.1% call `fig.show()`, 46.9% read a file or URL, 3.3% of prompts mention columns.
5. **The data.** A pipeline diagram:
   - 970 scraped rows, set aside as training data.
   - Claude Haiku wrote 180 table schemas and 2,880 questions, and Claude Sonnet wrote the code answers.
   - Every answer was run in the app's own sandbox against a real CSV and kept only if it rendered: 1,897 of 1,920.
   - 300 test questions on 60 schemas never seen in training were frozen.
   - lora-v1 trained on 1,929 rows. lora-v2 trained on 7,321, adding analyst and planner examples distilled from Claude Opus 5.5 (`c2e4cb7`).
   - Data cost $5.47 for v1 and $15.62 for v2.
6. **Training.**
   - LoRA on Qwen3.5-9B, on an A100 80 GB on Runpod at $2.19/h.
   - lora-v1: 2 h 24 m of pod time, validation loss 0.671 → 0.1767, $5.34 of cloud time.
   - lora-v2: 2 epochs, 1,832 steps, 3.3 h, validation loss 0.157 → 0.126, $8.42.
   - Converted from PEFT to MLX and served 4-bit on a Mac with `mlx_lm`. A validation-loss chart for both runs.
7. **Results.** One table. Each row names its test set and links to its source file on GitHub:
   - Frozen 300, full precision: renders 7.7% → 91.3% → 97.3%; right shape 4.7% → 81.0% → 87.0% (base → lora-v1 → lora-v2).
   - Frozen 300 on a Mac, 4-bit, one harness (`evaluate.py`, greedy, 1,024-token cap): base with thinking off → lora-v1 89.3% / 76.3% → lora-v2 94.3% / 82.3% (render / right kind; v1 → v2 paired p = 0.020). This is the headline row: same questions, same precision, same harness for all three.
   - 120 frozen dashboard requests: needing a retry 54.2% → 12.5%; drawn charts that render 86.4% → 98.9%; drawn as the planned kind 84.9% → 98.9%.
   - A note: 7.7% measures the essay. The fair baseline is the base model with thinking off on the same 300 questions, its best setting.
   - The 118-question set of `ab_planner_hint.json` is not on the page: it is weighted to the hardest chart types, and the frozen 300 now has a base row of its own.
8. **How the app works.** One diagram: analyst → planner → plan checks against the real tables (up to 3 tries) → chartist writes Plotly code → sandbox runs it → drawing check (up to 2 fixes) → narrator writes the title. With the rule: no hardcoded charts; every chart is the model's own code or is reported failed.
9. **Run it yourself.** Clone, `make setup`, `make serve-model`, `make up`. MLX needs Apple Silicon. Link to the README.
10. **Footer.** Built by @tukka25. Data credits: Inside Airbnb (CC BY 4.0), Spotify songs through TidyTuesday, the Netflix catalogue by Shivam Bansal on Kaggle through TidyTuesday. Base model: Qwen3.5-9B. The repository's licence, once part 2 chooses it.

### Sources of the numbers

| Numbers | Source |
|---|---|
| Frozen 300, full precision (base, lora-v1, lora-v2) | `chartist-finetune/cloud/README.md`, `cloud/eval_report.json`, `cloud/eval_report_v2.json` |
| Frozen 300 on a Mac | `chartist-finetune/data/eval_report_local_v1.json`, `eval_report_local_v2.json`; p = 0.020 from `cloud/README.md` |
| Frozen 300 on a Mac, base with thinking off | `chartist-finetune/data/eval_report_local_base_nothink.json` (key `base-nothink`), from `evaluate.py --no-thinking` (`c416ee1`) |
| 120 dashboard requests | `chartist-finetune/data/v2/planning_eval_lora-v1.json`, `planning_eval_lora-v2.json` |
| Scraped docs table, dataset sizes, data cost | `chartist-finetune/README.md`, `chartist-finetune/cloud/README.md`, `AGENTS.md` |
| Training time, loss, GPU cost | `chartist-finetune/cloud/README.md` |
| About $35 in all | sum of lora-v1 ($10.81) and lora-v2 ($15.62 data + $8.42 cloud) |

### The baseline run

Added at review, 2026-11-25. The base model, Qwen3.5-9B at 4-bit with no adapter and `enable_thinking=False`, scored on the frozen 300 by `evaluate.py`: the harness, test set (sha256 `bf385c59…`), token cap and decoding that produced lora-v1's and lora-v2's local reports. Base gets its best setting: with thinking on, its essay leaves almost no code inside the cap. Run on the Mac, under an hour, beside the idle model server.

## Making the three dashboards

A script, `backend/scripts/make_showcase.py` (`make showcase`). It follows the pattern of `make_chart_kind_examples.py`, which already writes model output into byd-web. Anyone can run it again.

### Sources

| Dashboard | Source | Into the app as |
|---|---|---|
| Airbnb | The latest Edinburgh snapshot from Inside Airbnb: `listings` and `reviews` (CC BY 4.0). Its `neighbourhoods` file lists only names, so it is left out. | Uploads: `listings.xlsx` (saved as Excel, which the page says) and `reviews.csv` |
| Spotify | The `spotify` Postgres database, table `tracks`: 32,833 songs. Rebuilt from the TidyTuesday 2020-01-21 file if missing. | A database connection |
| Netflix | `netflix_titles.csv` from the TidyTuesday 2021-04-20 mirror of the Kaggle dataset. Kaggle itself needs a login. | An upload |

- Uploaded files have no row limit in the app (the 500,000-row limit is for database tables). The page states each source's row count.
- Each licence and download URL is confirmed on the source's own page before the first download. A dataset whose terms do not clearly allow showing charts of it publicly is swapped. Spotify is checked hardest: its songs come from the Spotify Web API, whose developer terms apply. The fallback for the database dashboard is the shop demo, which also shows the app joining tables.
- Downloads go to a gitignored folder under `backend/uploads/`. No third-party data is committed.
- The first download needs the owner's OK, with each file's name, source and size.

### Prompts

| Dashboard | Prompt |
|---|---|
| Airbnb | thinking of renting out my flat in edinburgh on airbnb. which areas charge the most, entire place vs private room, and when are guests busiest? |
| Spotify | what makes a song popular? compare genres, energy vs danceability, and show me the top artists |
| Netflix | how has netflix changed over the years? movies vs tv shows, which countries make the most content, and the most common ratings |

### Building

1. Check that the app and the model server answer, and stop if either does not.
2. Use the script's own local account. The password comes from the environment and is never committed.
3. For each dashboard, create a new, empty report, so no earlier requests reach the planner, and add its sources.
4. Send the prompt as the dashboard `brief`, exactly as the app's prompt bar does.
5. Record the build's events: charts planned, drawn and skipped, and seconds.
6. Export the saved blocks to `site/data/dashboards/<name>.json`. Write to a temporary file and rename it, so a failed run never leaves a partial file.

### Quality bar

- A dashboard is accepted when every planned chart renders and none is visibly wrong: no stacked raw rows, no empty chart, no title that does not match its chart.
- If one falls short, the prompt changes the way a user would rephrase it, and the dashboard is built again. Charts are never edited.
- The page shows the prompt that produced the dashboard, and `build.prompts_tried` records how many came before it.
- A skipped chart is shown as such ("6 of 7 drawn"), never hidden.
- Each dashboard file stays under 1.5 MB. If one is larger (a scatter over every Spotify song, say), the prompt changes; the figure does not.

## Rendering

- **Dashboards:** the saved 12-column grid, with cards styled like the app's view mode. KPI blocks appear as the app's stat cards.
- **Plotly:** `plotly.js-dist-min`, at the version the app uses, is loaded once, when the dashboards section comes near the viewport.
- **Before Plotly loads:** each card shows its title and an empty frame of the right size, never an image standing in for the chart.
- **Charts:** the app's re-theme; hover on; zoom and the mode bar off.
- **Narrow screens** (under 768 px): one column, every chart at full width.
- **If Plotly fails to load:** the cards keep their titles with "Charts could not load", and the rest of the page works.
- **Hero animation:**
  - A canvas, with the timing and easing of the app's `BuildLoader`, looping through the 14 shapes.
  - With `prefers-reduced-motion`, one still shape.
  - Paused when off screen or when the tab is hidden.
  - Sized for the device pixel ratio.

## Tests and checks

- **`npm test` in `site/`** (Node's own runner, as in byd-web):
  - the four copies are byte-identical to their originals;
  - every entry in `stats.json` matches its source;
  - every dashboard file has a prompt, provenance, figures, grid positions within 12 columns, and stays under 1.5 MB.
- **byd-web:** its tests, lint and build still pass after the re-theme and the draw loop move into `lib/`, and the loader and the charts look the same in the running app.
- **Build:** `npm run lint` and `npm run build` (the static export) in `site/`.
- **In a browser:** desktop and phone widths, and with reduced motion. A performance check on the first Vercel preview.

## Vercel

The owner creates the project, since it needs their account. `site/README.md` gives the steps:

1. Import the repository.
2. Set the root directory to `site`; the framework is Next.js.
3. Set the ignored build step to `git diff --quiet HEAD^ HEAD -- .`
4. Deploy from `main`. It works while the repository is private and after it is public.

## Success criteria

- The page builds as a static site and deploys from `site/`.
- Every number on it passes the stats test.
- The three dashboards are the app's unedited output, each with the prompt that drew it, meeting the quality bar.
- The hero animation runs without end, and honours reduced motion.
- The page reads well at phone width.

## Needs the owner's OK during the build

- The first download of the source files.
- Pushing the branch, creating the Vercel project, and the first deploy.
