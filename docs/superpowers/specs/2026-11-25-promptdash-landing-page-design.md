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
| The three datasets | Airbnb Edinburgh (Excel and CSV files), a demo shop (Postgres, synthetic), the Netflix catalogue (one CSV). The shop replaced Spotify songs on 2026-11-25, because Spotify's developer terms rule out showing its data. |
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

1. **Hero.** Left: the name, one line on what PromptDash is (ask for a dashboard in plain words; a 9B model fine-tuned for Plotly writes every chart, on your own machine), a GitHub button and a link down to the dashboards. Three headline numbers: chart scripts that run and charts of the right kind, each as the base model's share → lora-v2's (69% → 94% and 46% → 82%), both on the frozen 300 at 4-bit on a Mac; and about $35 to train. Right: the dot animation, morphing through all 14 chart shapes without end.
2. **Three dashboards.** Each one live, styled like the app's view mode, with its prompt in a fixed box below it. Then the data source and its licence, and "drawn by lora-v2, unedited", with the date.
3. **Journey.** A strip of dated milestones read from `git log`, each citing its commit: the first commit (2026-03-07, `35e0ce4`), the training data (2026-11-19, `ac9d3b2`), lora-v1 (2026-11-20, `a0fd4d0`), dashboards planned by the model (2026-11-21, `a91d276`), lora-v2 (2026-11-22, `7c8bdf1`; its commits are dated the 22nd, not the 21st), no hardcoded charts (2026-11-23, `7deeaa3`), the bar drawing check (2026-11-25, `2d7af93`).
4. **The problem.**
   - Out of the box, Qwen3.5-9B answers with a reasoning essay, and 7.7% of its chart scripts run (frozen 300, full precision).
   - With thinking off, on the same 300 questions at 4-bit on a Mac, 68.7% of its scripts run and 46.3% draw the right kind of chart, against lora-v2's 94.3% and 82.3%. Its failures are mostly runtime errors and invented columns, not formatting.
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
   - Frozen 300 on a Mac, 4-bit, one harness (`evaluate.py`, greedy, 1,024-token cap): base with thinking off 68.7% / 46.3% → lora-v1 89.3% / 76.3% → lora-v2 94.3% / 82.3% (render / right kind; v1 → v2 paired p = 0.020). This is the headline row: same questions, same precision, same harness for all three.
   - 120 frozen dashboard requests: needing a retry 54.2% → 12.5%; drawn charts that render 86.4% → 98.9%; drawn as the planned kind 84.9% → 98.9%.
   - A note: 7.7% measures the essay. The fair baseline is the base model with thinking off on the same 300 questions, its best setting.
   - The 118-question set of `ab_planner_hint.json` is not on the page: it is weighted to the hardest chart types, and the frozen 300 now has a base row of its own.
8. **How the app works.** One diagram: analyst → planner → plan checks against the real tables (up to 3 tries) → chartist writes Plotly code → sandbox runs it → drawing check (up to 2 fixes) → narrator writes the title. With the rule: no hardcoded charts; every chart is the model's own code or is reported failed.
9. **Run it yourself.** Clone, `make setup`, `make serve-model`, `make up`. MLX needs Apple Silicon. Link to the README.
10. **Footer.** Built by @tukka25. Data credits, read from the dashboard files: Inside Airbnb (CC BY 4.0), the demo shop (synthetic, made for this project), the Netflix catalogue by Shivam Bansal on Kaggle through TidyTuesday (CC0). Base model: Qwen3.5-9B. The repository's licence, once part 2 chooses it.

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

Result (`5d8e024`): 68.7% render, 46.3% right kind of chart. Of its 94 failures, 67 are runtime errors and 12 invented columns; 6 are syntax errors, so formatting is a small share. On the four hard buckets it agrees with the 118-question run within a row or two.

## Making the three dashboards

A script, `backend/scripts/make_showcase.py` (`make showcase`). It follows the pattern of `make_chart_kind_examples.py`, which already writes model output into byd-web. Anyone can run it again.

### Sources

| Dashboard | Source | Into the app as |
|---|---|---|
| Airbnb | The latest Edinburgh snapshot from Inside Airbnb: `listings` and `reviews` (CC BY 4.0). Its `neighbourhoods` file lists only names, so it is left out. | Uploads: `listings.xlsx` (saved as Excel, which the page says) and `reviews.csv` |
| Shop | The `shop` Postgres database from `backend/scripts/make_relational_demo.py`: customers (200), orders (5,000), products (40), visits (2,000), seeded and synthetic. The app joins its tables by their declared keys. | A database connection |
| Netflix | `netflix_titles.csv` from the TidyTuesday 2021-04-20 mirror of the Kaggle dataset. Kaggle itself needs a login. | An upload |

- Uploaded files have no row limit in the app (the 500,000-row limit is for database tables). The page states each source's row count.
- Each licence and download URL is confirmed on the source's own page before the first download. A dataset whose terms do not clearly allow showing charts of it publicly is swapped. Spotify was checked hardest, and failed: its songs come from the Spotify Web API. Spotify's Developer Terms (version 10, effective 15 May 2025) count metadata as Spotify Content, say you "may not store, aggregate or create compilations or databases of Spotify Content", and keep Spotify's rights in derivative works. So the database dashboard uses the shop demo, which also shows the app joining tables (the owner's choice, 2026-11-25). The licences checked: Inside Airbnb states CC BY 4.0 on its get-the-data page; the Netflix dataset's Kaggle page states CC0.
- Downloads go to a gitignored folder under `backend/uploads/`. No third-party data is committed.
- The first download needs the owner's OK, with each file's name, source and size.

### Prompts

| Dashboard | Prompt |
|---|---|
| Airbnb | thinking of renting out my flat in edinburgh on airbnb. which areas charge the most, entire place vs private room, and when are guests busiest? |
| Shop | how is my shop doing? revenue by month, which product categories sell best, and which customer regions spend the most |
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
- Each dashboard file stays under 1.5 MB. If one is larger (a scatter over every row of a big table, say), the prompt changes; the figure does not.

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

## Revision 2 (2026-11-25, the owner, after the first build)

Replaces the parts above where they disagree.

- **No journey section.**
- **Dashboards as three cards** on the landing page: "Airbnb Dashboard", "Shop Dashboard", "Netflix Dashboard". Each card opens its own page (`/dashboards/<name>/`) with the full dashboard, a back link at the top left, and the frozen prompt at the bottom, as before. The landing page itself loads no Plotly.
- **No money anywhere.** Runpod and Claude may be named. Only before-and-after results stay as numbers: the hero's two improvements and one short results table, each still checked against its source. The story reads without figures, so the loss charts go.
- **The story** tells how the first data was gathered (a crawl of the Plotly docs that taught the wrong habits), how Claude Haiku, Sonnet and Opus were used to distil better data, that lora-v2 is one adapter trained for three jobs (writing chart code, the analyst, the planner), and how the app harnesses the model: the steps, the tools by name (`find_columns`, `inspect_column`, `relationship`, `preview_chart`, `row_grain`), the checks and repairs, and how it keeps the model's prompts short. Technical but readable, not jargon.
- **Wording** follows the `no-ai-slop` and `antislop-copywriting` skills; **layout** follows `antislop`, `antislop-ui` and `antislop-layoutmobile`.
- **Readability:** larger, darker body text.
- The final review's fixes ship with this revision (plan Part B).

## Revision 3 (2026-11-25, the owner, after the story rewrite)

Replaces the parts above where they disagree.

- **A preview on each card.** The owner asked for "a sneak peek photo of the graphs" on each dashboard card. Under its title, each card shows a picture of the top of that dashboard, captured from the dashboard's own page in headless Chrome by `site/scripts/previews.mjs` and committed as WebP. The "not screenshots" and "never an image standing in for the chart" rules now apply to the dashboard pages only: those still draw live Plotly charts. The landing page still loads no Plotly. A test fails when a dashboard file changes without a new preview.
- **The card look** follows the owner's reference (Kokonut UI's carousel cards), built natively with no new dependency and no carousel: a tall rounded image tile with the source kinds in a chip at its top left and an arrow chip at its top right, the title and the prompt under it, the middle card larger and higher, the side cards smaller, lower and tilted a little outward; one column on phones.
- **Tool names, corrected.** The default explore step (`PLANNER_TOOLS=on`) offers `find_columns`, `inspect_column`, `relationship` and `preview`; `preview_chart` and `row_grain` belong to the optional checking turn (`PLANNER_TOOLS=planner`). The page names all six with their modes.

## Revision 4 (2026-11-25, the owner, after reading the rewritten story)

Replaces the parts above where they disagree.

- **The page is a first-person story, like a blog post.** Order: hero, the three dashboards, the problem, fine-tuning and its results, 1. How the data was gathered, 2. Training, 3. Harness, Run it on your Mac, footer.
- **Hero:** the hook is the owner's line, a 9B model fine-tuned to build full dashboards and charts from one prompt, with your data never leaving your device. The before/after cards say in plain words what was measured, on what, and before and after what.
- **The problem** is privacy: analysing sensitive data with a cloud-hosted model sends it off the machine. Could a small local model do it? KPI cards show the base model's results, each labelled with its condition (thinking on at full precision; thinking off at 4-bit on a Mac). The old essay and scraped-habits paragraphs go.
- **Numbers are back** as KPI cards and the results table only, every one still read back from its source by the stats test. Money stays out.
- **The dashboards intro** says each dashboard came out of one run, plan to every chart, nothing edited. It does not say "first shot": two of the three prompts were reworded before the run shown, and each dashboard page says so.
- **Links:** Qwen3.5-9B's model page, Plotly, Runpod.
- **Footer:** GitHub profile, LinkedIn (shown once its URL is set), and the repository; data credits as links only, with the CC BY licence tag kept beside the Inside Airbnb link because that licence requires it.
- **The root README** is rewritten to be readable and to the point, with the setup the page points to.
- Tasks B5 (story), B6 (footer) and B7 (README) ran in parallel worktrees beside B4 (cards), then merged.

## Notes after the final review (2026-11-25)

Changes made by the controller and the review loop, not by the owner; recorded so the spec matches the code.

- **Card pictures** start at the dashboard's first chart, not its first block that is not a note: a KPI tile at the top left sat under the source chip. One rule for all three (`site/data/previews.json` states it).
- **Dashboard-page credits** are links, like the footer's, and name the dataset first ("Data: Inside Airbnb, listings.xlsx (converted from the CSV), reviews.csv · CC BY 4.0"): CC BY 4.0 requires naming the creator on the page that shows the material. Synthetic data links once, to its generating script.
- **Bar value labels** in the app's re-theme (`byd-web/lib/plot-theme.ts`, copied to the site) follow the bars' own largest value: SI with five significant figures from 1,000, at most two decimals from 1, two significant figures under 1. The showcase's "£50.667" now reads "£50.67". This changes every bar chart in the app.
- **Focus rings** follow each element's own radius (the global `:focus-visible` rule no longer sets one).
