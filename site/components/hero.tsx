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
            See the dashboards
          </a>
        </div>
        <dl className="mt-10 grid max-w-xl gap-3 sm:grid-cols-2">
          <Figure label="of chart scripts run" value={`${stat("base_render_mac", 0)} → ${stat("v2_render_mac", 0)}`} />
          <Figure
            label="draw the right kind of chart"
            value={`${stat("base_shape_mac", 0)} → ${stat("v2_shape_mac", 0)}`}
          />
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
