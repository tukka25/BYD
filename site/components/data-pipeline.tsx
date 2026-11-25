import type { ReactNode } from "react";
import { BODY, Code, Lede, MEASURE, Section } from "@/components/section";

/* Who made each part of the training data. Haiku and Sonnet: chartist-finetune/
   README.md; Opus and the held-out sets: export_v2.py, which also refuses a row
   from either frozen test set. */
const STEPS: Array<{ who: string; text: ReactNode }> = [
  {
    who: "Claude Haiku",
    text: "Wrote business table schemas, each backed by a real CSV, and the questions a person might ask of them.",
  },
  {
    who: "Claude Sonnet",
    text: (
      <>
        Answered each training question with Plotly code. An answer stayed only if it ran against its CSV in a
        sandbox that mirrors the app&apos;s, and passed the app&apos;s checks.
      </>
    ),
  },
  {
    who: "Claude Opus",
    text: (
      <>
        Wrote the planning examples: the analyst&apos;s directions and the planner&apos;s chart plans. Each one
        passes the app&apos;s plan check against its real table.
      </>
    ),
  },
  {
    who: "Held-out tests",
    text: (
      <>
        Two test sets, one of chart questions and one of dashboard requests, use tables that never appear in
        training. The script that builds the training data stops if a row comes from one of them.
      </>
    ),
  },
];

/* The three roles lora-v2 plays, in the order a dashboard needs them. */
const ROLES: Array<{ role: string; reads: ReactNode; writes: ReactNode; by: string }> = [
  { role: "Analyst", reads: "A profile of the tables and the request", writes: "Directions worth charting", by: "Claude Opus" },
  { role: "Planner", reads: "The profile and the analyst's directions", writes: "A plan for every chart", by: "Claude Opus" },
  {
    role: "Chartist",
    reads: <>A question or a chart plan, and the table&apos;s columns</>,
    writes: (
      <>
        Plotly code, ending in <Code>print(fig.to_json())</Code>
      </>
    ),
    by: "Claude Sonnet, and the rewritten docs",
  },
];

const COLUMNS = "lg:grid-cols-[7.5rem_minmax(0,1fr)_minmax(0,1fr)_11rem]";

export function DataPipeline() {
  return (
    <Section id="data" title="1. How the data was gathered">
      <div className="space-y-5">
        <Lede>
          The first training data came from Plotly&apos;s own documentation, a Scrapy crawl of plotly.com/python.
          Those examples are written for people reading the docs. Almost all of them show the chart on screen, and
          none prints it as JSON, the only form the app can read.
        </Lede>
        <Lede>
          I distilled new training data from Claude instead, and kept only what passed the app&apos;s own checks.
          Part of the crawl stayed too, rewritten to pass them.
        </Lede>
      </div>

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
          <span>Role</span>
          <span>Reads</span>
          <span>Writes</span>
          <span>Examples written by</span>
        </div>
        <dl>
          {ROLES.map((role) => (
            <div key={role.role} className={`grid gap-1.5 border-b px-5 py-5 last:border-0 sm:px-6 lg:gap-6 ${COLUMNS}`}>
              <dt className="font-display text-[18px] font-semibold text-ink">{role.role}</dt>
              <Cell label="Reads">{role.reads}</Cell>
              <Cell label="Writes">{role.writes}</Cell>
              <Cell label="Examples written by">{role.by}</Cell>
            </div>
          ))}
        </dl>
      </div>
    </Section>
  );
}

/* A cell of the roles table. Its column name shows beside it below `lg`, where
   the header row is hidden, and stays for screen readers above that. */
function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <dd className={`text-[16px] leading-relaxed text-ink ${MEASURE}`}>
      <span className="font-semibold text-body lg:sr-only">{label}: </span>
      {children}
    </dd>
  );
}
