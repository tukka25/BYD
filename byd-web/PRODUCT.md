# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People who find the project on GitHub and run it on their own machine. The author
is open-sourcing the build publicly, so the first audience is developers and
data-literate people evaluating whether a local-first BI tool is credible, then
running it against their own CSV or Excel exports.

Inside the product, the user is working alone: upload a file, ask a question in
plain English, get a chart. Single user today; nothing in the data model forbids
more later, but no sharing or permissions exist.

## Product Purpose

Turn a natural-language question about a dataset into a working chart, without
the user writing SQL, pandas or Plotly, and without the data leaving their
machine. Success is a correct, runnable chart from a plain question — and a
report assembled from several of them.

## Positioning

**Nothing leaves the machine.** The model runs locally — Ollama, or `mlx_lm
server` with a fine-tuned adapter on Apple silicon — and the data, the schema and
the generated code never reach a hosted API. This is the claim a cloud BI tool
cannot copy, and it is the reason to choose this over one.

The model is fine-tuned for this specific job rather than prompted into it:
measured 91.3% render rate on a frozen 300-question test set, against 7.7% for
the same base model untuned.

## Operating Context

Run locally via `make up` (Postgres + API + web in Docker) with the model served
on the host, because Metal cannot run in a container. Users upload `.csv`,
`.xls` or `.xlsx` files. Charts are produced by generating Python, executing it
in a sandboxed subprocess against the real dataframe, and rendering the resulting
Plotly figure — so a chart that appears has demonstrably run.

## Capabilities and Constraints

- **Fully local, no cloud. Binding.** No hosted services, no telemetry, and no
  third-party CDN or webfont requests at runtime. The current build violates this
  in two places — Plotly is loaded from `cdn.plot.ly` and Inter from Google Fonts
  — and both must be self-hosted.
- Local model backends: Ollama (`/api/chat`) or `mlx_lm server`
  (OpenAI-compatible). Selected by `LLM_BACKEND`.
- Existing and preserved: JWT auth, `users` / `data_sources` / `dashboards`
  tables, file upload, the agent workflow (planner → source detection → chartist
  → sandboxed executor), and the chartist's prompt contract, which the model was
  fine-tuned against and must not drift.
- Charts are Plotly figures produced from generated Python. The system already
  validates generated code against a contract and falls back to a deterministic
  chart when the model's output is unusable.
- Generation is not instant: roughly 13–15s per chart on an M2 Pro. The interface
  has to make waiting legible.

## Brand Commitments

Name in the current build: PromptDash. No logo, wordmark, or brand assets exist
yet. No confirmed voice guidelines.

## Evidence on Hand

- Measured eval: 91.3% render rate, 81.0% correct chart type, n=300 frozen test
  set; base model 7.7% / 4.7%. Recorded in `chartist-finetune/cloud/README.md`.
- Four generated sample datasets in `backend/uploads/` (SaaS revenue, ecommerce
  orders, property sales, web traffic) with a generator script.
- No real customers, testimonials, benchmarks against named competitors, or
  pricing exist. Future work must not invent them.

## Product Principles

1. **Local is the promise, so show it.** Where a hosted tool would hide
   infrastructure, this one can state that the model and the data are on this
   machine. Never introduce a runtime dependency on an external service.
2. **The executed chart is the proof.** Every chart shown has actually run
   against the real data. Favour showing the real result over a preview or mock.
3. **Questions, not query builders.** The input is a sentence. Do not drift
   toward field pickers and semantic layers; that is the thing being replaced.
4. **Be honest about the wait and about failure.** Generation takes seconds and
   sometimes falls back. Surface which, rather than presenting a fallback chart
   as a model result.
5. **Credible to someone reading the source.** The audience arrives from GitHub
   and will judge it as an engineer. Precision beats decoration.

## Accessibility & Inclusion

No product-specific requirement established. Treat standard WCAG AA contrast and
keyboard operability as the floor, with particular attention to the canvas:
drag-and-resize interactions need keyboard and screen-reader equivalents.
