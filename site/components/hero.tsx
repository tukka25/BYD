import { DotHero } from "@/components/dot-hero";
import { GitHubMark } from "@/components/icons";
import { stat } from "@/components/numbers";
import { CAPTION, MEASURE, Name } from "@/components/section";
import { REPO_URL } from "@/lib/site";

export function Hero() {
  return (
    <header className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-12 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pb-24 lg:pt-20">
      <div>
        <h1 className="font-display text-[44px] font-bold leading-[1.02] sm:text-[60px]">PromptDash</h1>
        <p className="mt-5 max-w-xl text-[19px] leading-[1.6] text-ink text-pretty sm:text-[21px]">
          Ask for a dashboard in plain words. A 9B model, fine-tuned to write Plotly, draws every chart on your own
          Mac.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <a
            href={REPO_URL}
            className="inline-flex h-11 items-center gap-2 rounded-[var(--r-pill)] bg-pine px-5 text-[15px] font-semibold text-white shadow-[var(--lift-1)] transition-colors hover:bg-[var(--pine-press)] active:translate-y-px"
          >
            <GitHubMark />
            View on GitHub
          </a>
          <a
            href="#dashboards"
            className="inline-flex h-11 items-center rounded-[var(--r-pill)] bg-surface px-5 text-[15px] font-semibold text-ink ring-1 ring-inset ring-hairline transition-colors hover:bg-sunken active:translate-y-px"
          >
            See the dashboards
          </a>
        </div>
        <dl className="mt-10 grid max-w-xl gap-3 sm:grid-cols-2">
          <Figure label="chart scripts that run" value={`${stat("base_render_mac", 0)} → ${stat("v2_render_mac", 0)}`} />
          <Figure label="charts of the right kind" value={`${stat("base_shape_mac", 0)} → ${stat("v2_shape_mac", 0)}`} />
        </dl>
        <p className={`mt-3 ${MEASURE} ${CAPTION}`}>
          Base <Name>Qwen3.5-9B</Name> with thinking off, then with <Name>lora-v2</Name>, on the same frozen test
          questions, <Name>4-bit</Name> on a Mac.{" "}
          <a href="#results" className="font-semibold text-pine underline underline-offset-2 hover:text-[var(--pine-press)]">
            All the results
          </a>
        </p>
      </div>
      <DotHero />
    </header>
  );
}

/* Label first in the DOM, as a definition list wants; on wider screens the
   number shows above it. On a phone each figure is one row. A figure never
   breaks across lines. */
function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 rounded-[var(--r-card)] bg-surface px-4 py-3 shadow-[var(--lift-1)] sm:flex-col-reverse sm:items-start sm:justify-end sm:py-4">
      <dt className="text-[15px] leading-snug text-body">{label}</dt>
      <dd className="whitespace-nowrap font-display text-[22px] font-bold leading-tight text-ink tabular sm:text-[26px]">
        {value}
      </dd>
    </div>
  );
}
