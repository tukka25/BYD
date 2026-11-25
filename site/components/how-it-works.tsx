import type { ReactNode } from "react";
import { BODY, CAPTION, Code, Lede, MEASURE, Section } from "@/components/section";

type Step = { name: string; text: ReactNode };

const PLANNING: Step[] = [
  {
    name: "Profile",
    text: "The app describes each table from a sample of rows spread across the whole table: every column's role and a few of its values, read from the values alone.",
  },
  {
    name: "Explore",
    text: (
      <>
        The model may check up to three facts with four tools: <Code>find_columns</Code>, <Code>inspect_column</Code>,{" "}
        <Code>relationship</Code> and <Code>preview</Code>. What they find goes on as a short note.
      </>
    ),
  },
  { name: "Analyst", text: "Reads the profiles, the note and the request, and proposes what is worth charting." },
  {
    name: "Planner",
    text: "Writes the plan for every chart in one reply: kind, table, x and y, grouping, aggregation, time grain, sort, how many to keep, and a title.",
  },
  {
    name: "Plan checks",
    text: "Code tests every column against the real tables, then the data itself: too many bars or slices for one chart, or a line whose x repeats so it would run back and forth. Problems go back to the planner in plain words, for up to three tries, and the best try is kept.",
  },
];

const DRAWING: Step[] = [
  { name: "Chartist", text: "lora-v2 writes the Plotly code for one plan." },
  { name: "Sandbox", text: "The code runs on the real table. An error goes back to the model with its own code." },
  {
    name: "Drawing check",
    text: "Code reads the finished figure. A line that runs back and forth, or bars that stack raw rows, go back to the model too.",
  },
];

const TOOLS: Array<{ name: string; answers: string; where: string }> = [
  { name: "find_columns", answers: "Which columns, in any table, match a word by name or by their common values", where: "Both" },
  {
    name: "inspect_column",
    answers: "Facts about one column on the full table: its kind, distinct values, empty cells, quartiles, top values, and whether values repeat",
    where: "Both",
  },
  {
    name: "relationship",
    answers: "How two columns relate: a correlation, a mean per group, or the combinations present",
    where: "Both",
  },
  {
    name: "preview",
    answers: "What a chart over some columns would show on the real data, including whether a sum would add up repeated rows",
    where: "Explore step",
  },
  { name: "row_grain", answers: "Which columns identify one row, such as one row per weekday and hour", where: "Checking turn" },
  {
    name: "preview_chart",
    answers: "What up to seven draft plans would draw, one line each, with any problem the plan check would raise",
    where: "Checking turn",
  },
];

const SHORT: ReactNode[] = [
  "The model reads a profile built from a sample of rows.",
  "Tool results are cut to a fixed size and marked where they were cut. The analyst and the planner see only a short note of what the tools found.",
  "One reply plans every chart on the dashboard.",
  "Thinking is off for the analyst and the planner. With thinking on, the base model spent the planner's whole budget on an essay.",
  "A fix sends back the model's own code and what went wrong, in plain words.",
  <>
    In the checking turn, the drafts are numbered, and <Code>preview_chart</Code> takes their numbers, so the model
    does not type every plan out again.
  </>,
];

export function HowItWorks() {
  return (
    <Section id="how" title="How the app runs the model">
      <Lede>
        The model never sees a whole table, and code checks its work at every step. A dashboard is built in two
        passes: first the plan for every chart, then each chart drawn from its plan.
      </Lede>

      <div className="mt-10 grid gap-4 lg:grid-cols-[1.15fr_1fr] lg:gap-6">
        <Phase title="Planning" steps={PLANNING} start={1} />
        <div className="flex flex-col gap-4 lg:gap-6">
          <Phase title="Drawing each chart" steps={DRAWING} start={PLANNING.length + 1} />
          <p className={`rounded-[var(--r-card)] bg-pine-wash px-6 py-5 ${BODY}`}>
            <strong className="font-semibold">No hardcoded charts.</strong> Every chart on a dashboard is the
            model&apos;s own code. A chart gets two fixes at most; if it still fails, the app reports it as failed,
            with the reason, and no template stands in for it.
          </p>
        </div>
      </div>

      <div className="mt-14 grid gap-12 lg:grid-cols-2 lg:gap-10">
        <div>
          <h3 className="font-display text-[22px] font-semibold leading-tight sm:text-[24px]">The tools</h3>
          <p className={`mt-3 ${BODY}`}>
            By default an explore step holds the first four tools. The other mode,{" "}
            <Code>PLANNER_TOOLS=planner</Code>, lets the planner draft with no tools, because lora-v2&apos;s planner
            calls none under the prompt it was trained on. A separate checking turn then holds five tools and sends back
            only the plans that need a change. On the same frozen dashboard requests the two modes tied on quality, and
            the default stayed.
          </p>
          <dl className="mt-5 overflow-hidden rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
            {TOOLS.map((tool) => (
              <div key={tool.name} className="border-b px-5 py-4 last:border-0 sm:px-6">
                <dt className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <code className="font-mono text-[15px] font-medium text-ink">{tool.name}</code>
                  <span className="text-[14px] text-body">{tool.where}</span>
                </dt>
                <dd className="mt-1 text-[16px] leading-relaxed text-ink">{tool.answers}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h3 className="font-display text-[22px] font-semibold leading-tight sm:text-[24px]">
            Keeping the prompts short
          </h3>
          <ul className={`mt-4 list-disc space-y-3 pl-5 marker:text-pine ${MEASURE} ${BODY}`}>
            {SHORT.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      </div>

      <p className={`mt-12 ${MEASURE} ${CAPTION}`}>
        A single chart asked for in the ask bar takes a shorter path through the same chartist, sandbox and checks: a
        detective picks its table and a narrator writes its title.
      </p>
    </Section>
  );
}

function Phase({ title, steps, start }: { title: string; steps: Step[]; start: number }) {
  return (
    <div className="rounded-[var(--r-panel)] bg-surface p-6 shadow-[var(--lift-1)] sm:p-7">
      <h3 className="font-display text-[22px] font-semibold leading-tight sm:text-[24px]">{title}</h3>
      <ol start={start} className="mt-5 space-y-5">
        {steps.map((step, index) => (
          <li key={step.name} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2">
            <span aria-hidden="true" className="font-display text-[17px] font-semibold leading-[1.6] text-pine tabular">
              {start + index}
            </span>
            <div>
              <p className="font-display text-[18px] font-semibold leading-snug text-ink">{step.name}</p>
              <p className="mt-1 text-[16px] leading-relaxed text-ink sm:text-[17px]">{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
