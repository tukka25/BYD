import { DotHero } from "@/components/dot-hero";
import { GitHubMark } from "@/components/icons";
import { MeterCard } from "@/components/meter-card";
import { Num } from "@/components/num";
import { CAPTION, LINK, MEASURE, Name } from "@/components/section";
import { REPO_URL } from "@/lib/site";

/* Before is the base model with thinking off and after is lora-v2, on the
   same questions, the same Mac and the same 4-bit weights. The base model with
   thinking on scores far lower, but on other hardware and mostly because of
   its reasoning mode, so it belongs to the story, not to this comparison. */
export function Hero() {
  return (
    <header className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-12 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pb-24 lg:pt-20">
      <div>
        <h1 className="font-display text-[44px] font-bold leading-[1.02] sm:text-[60px]">PromptDash</h1>
        <p className="mt-5 max-w-xl text-[19px] leading-[1.6] text-ink text-pretty sm:text-[21px]">
          A 9B model fine-tuned to build full dashboards and charts from one prompt. Your data never leaves your
          device.
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
        <div className="mt-10 grid max-w-xl gap-3 sm:grid-cols-2">
          <MeterCard
            title="Code that ran and drew a chart"
            note={
              <>
                <Num id="test_questions" /> chart questions it never saw in training
              </>
            }
            meters={[
              { label: "Before fine-tuning", id: "base_render_mac" },
              { label: "After", id: "v2_render_mac", tuned: true },
            ]}
          />
          <MeterCard
            title="Charts of the kind asked for"
            note="The same questions"
            meters={[
              { label: "Before fine-tuning", id: "base_shape_mac" },
              { label: "After", id: "v2_shape_mac", tuned: true },
            ]}
          />
        </div>
        <p className={`mt-3 ${MEASURE} ${CAPTION}`}>
          Before is the base <Name>Qwen3.5-9B</Name> with thinking off. After is my fine-tune, <Name>lora-v2</Name>.
          Both ran <Name>4-bit</Name> on a Mac.{" "}
          <a href="#results" className={LINK}>
            All the results
          </a>
        </p>
      </div>
      <DotHero />
    </header>
  );
}
