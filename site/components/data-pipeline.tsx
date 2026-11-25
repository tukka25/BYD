import type { ReactNode } from "react";
import { BODY, Code, Lede, MEASURE, Section } from "@/components/section";

/* In the order it happened. Each line names who did the work. */
const STEPS: Array<{ who: string; text: ReactNode }> = [
  {
    who: "The crawl",
    text: <>Part of it stayed in the training data, rewritten so every example passes the app&apos;s contract.</>,
  },
  {
    who: "Claude Haiku",
    text: "Wrote business table schemas, each backed by a real CSV, and the questions a person might ask of them.",
  },
  {
    who: "Claude Sonnet",
    text: (
      <>
        Answered each training question with Plotly code. Each answer ran against its CSV in a sandbox that mirrors
        the app&apos;s, and stayed only if it passed the app&apos;s own contract check and its figure checked out.
      </>
    ),
  },
  {
    who: "Two test sets",
    text: (
      <>
        One holds single-chart questions and the other dashboard requests, all on tables that never appear in
        training. The script that builds the training data stops if a row comes from one of those tables.
      </>
    ),
  },
  {
    who: "lora-v1",
    text: (
      <>
        Trained only to write chart code, on Sonnet&apos;s answers and the rewritten docs. Its dashboard plans often
        failed the app&apos;s checks and needed another try. It had also barely seen a funnel, a sunburst or a
        waterfall, because the examples meant for those kinds came back almost all treemaps.
      </>
    ),
  },
  {
    who: "Claude Opus",
    text: (
      <>
        Wrote examples of the two planning jobs. The analyst reads a profile of the tables and a request and says
        what is worth charting; the planner turns that into a plan for every chart. Every example passes the
        app&apos;s own plan check against its real table, with no errors.
      </>
    ),
  },
  {
    who: "lora-v2",
    text: (
      <>
        Trained on all of it. The chart code comes in two forms, with a question as the task and with a chart plan,
        which is how the planner hands work to the chartist. New examples add funnels, sunbursts, waterfalls and KPI
        cards.
      </>
    ),
  },
];

const JOBS: Array<{ job: string; reads: ReactNode; writes: ReactNode; by: string }> = [
  {
    job: "Chartist",
    reads: <>A question or a chart plan, and the table&apos;s columns</>,
    writes: (
      <>
        Plotly code, ending in <Code>print(fig.to_json())</Code>
      </>
    ),
    by: "Claude Sonnet, and the rewritten docs",
  },
  { job: "Analyst", reads: "A profile of the tables and the request", writes: "Directions worth charting", by: "Claude Opus" },
  { job: "Planner", reads: "The profile and the analyst's directions", writes: "A plan for every chart", by: "Claude Opus" },
];

const COLUMNS = "lg:grid-cols-[7.5rem_minmax(0,1fr)_minmax(0,1fr)_11rem]";

export function DataPipeline() {
  return (
    <Section id="data" title="Training data, written by Claude and checked by the app">
      <Lede>
        Every training example is a job the app gives the model, paired with an answer that passed the app&apos;s
        own checks. Claude wrote most of them, in steps.
      </Lede>

      <dl className="mt-10 space-y-7">
        {STEPS.map((step) => (
          <div key={step.who} className="md:grid md:grid-cols-[10rem_minmax(0,1fr)] md:gap-x-10">
            <dt className="font-display text-[19px] font-semibold leading-snug text-ink md:pt-0.5">{step.who}</dt>
            <dd className={`mt-1.5 md:mt-0 ${MEASURE} ${BODY}`}>{step.text}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mt-14 font-display text-[22px] font-semibold leading-tight sm:text-[24px]">
        One adapter, three jobs
      </h3>
      <div className="mt-5 overflow-hidden rounded-[var(--r-card)] bg-surface shadow-[var(--lift-1)]">
        <div
          aria-hidden="true"
          className={`hidden gap-6 border-b px-6 py-3 text-[14px] font-semibold text-body lg:grid ${COLUMNS}`}
        >
          <span>Job</span>
          <span>Reads</span>
          <span>Writes</span>
          <span>Examples written by</span>
        </div>
        <dl>
          {JOBS.map((job) => (
            <div key={job.job} className={`grid gap-1.5 border-b px-5 py-5 last:border-0 sm:px-6 lg:gap-6 ${COLUMNS}`}>
              <dt className="font-display text-[18px] font-semibold text-ink">{job.job}</dt>
              <Cell label="Reads">{job.reads}</Cell>
              <Cell label="Writes">{job.writes}</Cell>
              <Cell label="Examples written by">{job.by}</Cell>
            </div>
          ))}
        </dl>
      </div>
    </Section>
  );
}

/* A cell of the jobs table. Its column name shows beside it below `lg`, where
   the header row is hidden, and stays for screen readers above that. */
function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <dd className="text-[16px] leading-relaxed text-ink">
      <span className="font-semibold text-body lg:sr-only">{label}: </span>
      {children}
    </dd>
  );
}
