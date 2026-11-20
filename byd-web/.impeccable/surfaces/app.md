---
version: 1
slug: "app"
primary_target: "app"
related_targets: []
---

Scope: the whole signed-in application — app shell, reports list, data sources, and the report canvas. Visitor mode: Operate.

Audience: someone who found this on GitHub and runs it on their own machine. Job: upload a file, ask a question in plain English, assemble the answers into a report they can export. Constraint from PRODUCT.md: fully local, no cloud — no CDN scripts, no remote webfonts.

Memorable moment: the Ask bar is always present at the foot of the canvas. A question typed there becomes a block on the grid; the block shows the code it ran, because the proof is that it executed.

Unresolved: whether KPI blocks come from the model as Plotly indicators or as a separate card type (to be measured, not assumed).

## Direction contract

THESIS: A report is assembled, not configured — every block on the canvas is proof that code ran on this machine against this file. It refuses the admin-template arrangement of boxed KPI tiles above a fixed chart grid, and refuses the BI console's field-picker and semantic layer.

OWN-WORLD: Light neutral canvas with near-white surfaces, separated by value rather than borders or shadows. 24px card radius, pill controls, circular ghost icon buttons. Violet primary, amber accent, coral third series. Geometric sans: very large heavy numerals and headings, small grey eyebrow labels above every title. Charts speak the same language — pill-capped bars with vertical gradient, thick round-capped lines.

STORY: The visitor understands the model and the data are on this machine, believes the chart because it executed, and leaves with an exported report.

FIRST VIEWPORT: Fixed 248px sidebar — wordmark, Reports group listing named reports, Data group. Canvas header: eyebrow then large report title, source chip, Edit/View toggle, Export. Body: snapping grid of blocks on grey. Foot: a persistent Ask bar centred above the canvas edge, the primary action, never floating over a block.

FORM: seed: none (pinned). Pinned by the user in these words: "check this design its veery nice put in the references"; "make it like you know grafana kind of"; "use like react flow only design wise not functinoaility"; "see like this photo make a sidebar for navigatino put the important thing anf underdashboard you can make multiple reports"; "change the color pallete we have and the icons and font all of them are bad".

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
