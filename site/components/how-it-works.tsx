import type { ReactNode } from "react";
import { BODY, Code, Lede, MEASURE, Section } from "@/components/section";

type Step = { name: string; text: ReactNode };

/* From profile to drawn chart (AGENTS.md: the AI dashboard flow, the planner
   tools, the drawing check and NO HARDCODED CHARTS). */
const PLANNING: Step[] = [
  {
    name: "Profile",
    text: "The app describes each table from a sample of rows spread across it, read from the values alone.",
  },
  {
    name: "Explore",
    text: "The model checks up to three facts with its tools, and what they find goes on as a short note.",
  },
  { name: "Analyst", text: "Proposes what is worth charting, from the profiles, the note and the request." },
  {
    name: "Planner",
    text: "Writes the plan for every chart in one reply: kind, columns, grouping, aggregation, sort and title.",
  },
  {
    name: "Plan checks",
    text: "Code tests every column against the real tables, then the data: too many bars or slices, or a line that would run back and forth. Problems go back to the planner in plain words, for up to three tries.",
  },
];

const DRAWING: Step[] = [
  { name: "Chartist", text: "Writes the Plotly code for one plan." },
  { name: "Sandbox", text: "Runs the code on the real table." },
  {
    name: "Drawing check",
    text: "Code reads the finished figure and sends back a line that runs back and forth, or bars that stack raw rows.",
  },
];

/* By mode, with the names data_tools.py gives them (EXPLORER_TOOL_NAMES and
   PLANNER_TOOL_NAMES): the checking turn swaps preview for row_grain and
   preview_chart and keeps the other three. */
const TOOL_MODES: Array<{ mode: ReactNode; tools: Array<{ name: string; answers: string }> }> = [
  {
    mode: "Explore step, the default",
    tools: [
      { name: "find_columns", answers: "Columns, in any table, that match a word by name or by their values" },
      { name: "inspect_column", answers: "Facts about one column, read on the full table" },
      { name: "relationship", answers: "How two columns relate" },
      { name: "preview", answers: "What a chart over some columns would show on the real data" },
    ],
  },
  {
    mode: (
      <>
        Checking turn, <code className="font-mono text-[14px] font-medium">PLANNER_TOOLS=planner</code>
      </>
    ),
    tools: [
      { name: "row_grain", answers: "Which columns identify one row" },
      { name: "preview_chart", answers: "What the draft plans would draw, with any problem the plan check would raise" },
      { name: "find_columns, inspect_column, relationship", answers: "The same three as in the explore step" },
    ],
  },
];

const SHORT: string[] = [
  "Tool results are cut to a fixed size and marked where they were cut.",
  "The analyst and the planner see only a short note of what the tools found.",
  "One reply plans every chart on the dashboard.",
  "Thinking is off for the analyst and the planner, so a reply is the answer alone, with no reasoning written out first.",
  "A fix sends back the model's own code and what went wrong, in plain words.",
];

export function HowItWorks() {
  return (
    <Section id="how" title="3. Harness">
      <Lede>
        This is the code around the model. It builds the prompts, and it checks the plans and the charts against the
        real data.
      </Lede>

      <div className="mt-10 grid max-w-[44rem] gap-4 lg:max-w-none lg:grid-cols-[1.15fr_1fr] lg:gap-6">
        <Phase title="Planning" steps={PLANNING} start={1} />
        <div className="flex flex-col gap-4 lg:gap-6">
          <Phase title="Drawing each chart" steps={DRAWING} start={PLANNING.length + 1} />
          <p className={`rounded-[var(--r-card)] bg-pine-wash px-6 py-5 ${BODY}`}>
            <span className={`block ${MEASURE}`}>
              <strong className="font-semibold">No hardcoded charts.</strong> A broken chart goes back to the model
              with its own code and what went wrong, at most twice. If it still fails, the app reports it as failed,
              with the reason.
            </span>
          </p>
        </div>
      </div>

      <div className="mt-14 grid max-w-[44rem] gap-12 lg:max-w-none lg:grid-cols-2 lg:gap-10">
        <div>
          <h3 className="font-display text-[22px] font-semibold leading-tight sm:text-[24px]">Tool calling</h3>
          <p className={`mt-3 ${MEASURE} ${BODY}`}>
            By default, an explore step before the analyst offers the model four tools. The other mode,{" "}
            <Code>PLANNER_TOOLS=planner</Code>, drops that step: the planner drafts with no tools, then a separate
            checking turn holds five and sends back only the plans that need a change.
          </p>
          <div className="mt-5 overflow-hidden rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
            {TOOL_MODES.map((group, index) => (
              <div key={index} className="border-b px-5 py-4 last:border-0 sm:px-6">
                <p className="text-[14px] font-semibold text-body">{group.mode}</p>
                <dl className="mt-3 space-y-3">
                  {group.tools.map((tool) => (
                    <div key={tool.name}>
                      <dt>
                        <code className="font-mono text-[15px] font-medium text-ink">{tool.name}</code>
                      </dt>
                      <dd className={`mt-0.5 text-[16px] leading-relaxed text-ink ${MEASURE}`}>{tool.answers}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="font-display text-[22px] font-semibold leading-tight sm:text-[24px]">
            Keeping the prompts short
          </h3>
          <ul className={`mt-4 list-disc space-y-3 pl-5 marker:text-pine ${MEASURE} ${BODY}`}>
            {SHORT.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
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
              <p className={`mt-1 ${MEASURE} ${BODY}`}>{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
