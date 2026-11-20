"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Code2, Cpu, Database, FileSpreadsheet, Sparkles } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { DotWave } from "@/components/dot-wave";
import { Plot } from "@/components/plot";
import { Button, Chip, EmptyState, Panel, inputClass } from "@/components/ui";
import { RichText } from "@/components/rich-text";
import { getAccessToken } from "@/lib/auth";
import { listSources, listTables, type Source } from "@/lib/sources";
import {
  listEngines,
  opusCost,
  runComparison,
  type CellResult,
  type ComparisonPlan,
  type Engine,
  type EngineInfo,
  type PlannedChart,
} from "@/lib/comparison";

/* Same question, same data, same contract, same executor — two sets of
   weights. The page exists to make that comparison legible, which means
   showing the failures as plainly as the charts. */

const ROW_HEIGHT = 30;

/* A run takes minutes and costs real money, so it survives a reload. Kept in
   sessionStorage rather than the database on purpose: a comparison is still an
   experiment, and it should not outlive the tab it was run in. Figures can be
   large, so a quota failure is ignored rather than allowed to break the page. */
const CACHE_KEY = "promptdash_last_comparison";

type Cached = { plan: ComparisonPlan; cells: CellResult[] };

function readCache(): Cached | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as Cached) : null;
  } catch {
    return null;
  }
}

function writeCache(value: Cached): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(value));
  } catch {
    // Over quota: the run is still on screen, it just will not come back.
  }
}

/** One side's whole dashboard, laid out on the plan both sides were given. */
function Dashboard({
  sections,
  cells,
}: {
  sections: PlannedChart[];
  cells: Map<number, CellResult>;
}) {
  return (
    <div className="grid grid-cols-12 gap-3">
      {sections.map((section) => (
        <div
          key={section.index}
          style={{
            gridColumn: `span ${Math.min(12, section.w)} / span ${Math.min(12, section.w)}`,
            minHeight: section.h * ROW_HEIGHT,
          }}
        >
          <Panel className="flex h-full flex-col p-3">
            <p className="mb-1.5 truncate text-[12px] font-semibold text-muted" title={section.question}>
              {section.question}
            </p>
            <div className="min-h-0 flex-1">
              <Cell cell={cells.get(section.index)} height={section.h * ROW_HEIGHT - 44} />
            </div>
          </Panel>
        </div>
      ))}
    </div>
  );
}

function Cell({ cell, height }: { cell: CellResult | undefined; height: number }) {
  const [showCode, setShowCode] = useState(false);

  if (!cell) {
    return (
      <div style={{ height }}>
        <DotWave label="Working…" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {cell.ok ? (
          <Chip tone="pine">
            <Check size={11} strokeWidth={3} />
            Rendered
          </Chip>
        ) : (
          <Chip tone="coral">
            <AlertTriangle size={11} strokeWidth={2.25} />
            Failed
          </Chip>
        )}
        {cell.used_fallback ? <Chip tone="copper">Fallback</Chip> : null}
        {cell.violations.length > 0 ? (
          <Chip tone="copper">{cell.violations.join(", ")}</Chip>
        ) : null}
        <span className="text-[12px] text-muted tabular">{cell.seconds.toFixed(1)}s</span>
        {cell.output_tokens > 0 ? (
          <span className="text-[12px] text-muted tabular">
            {cell.input_tokens.toLocaleString()} in · {cell.output_tokens.toLocaleString()} out
          </span>
        ) : null}
        {cell.code ? (
          <button
            onClick={() => setShowCode((v) => !v)}
            className="ml-auto inline-flex items-center gap-1 text-[12px] font-semibold text-pine"
          >
            <Code2 size={12} strokeWidth={2.25} />
            {showCode ? "Hide code" : "Code"}
          </button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1">
        {showCode ? (
          <pre className="h-[300px] overflow-auto rounded-[var(--r-card)] bg-inverse p-3 font-mono text-[11px] leading-relaxed text-on-dark">
            <code>{cell.code}</code>
          </pre>
        ) : cell.ok && cell.figure ? (
          <div className="h-[300px]">
            <Plot figure={cell.figure} />
          </div>
        ) : (
          <div className="flex h-[300px] items-start gap-2 rounded-[var(--r-card)] bg-coral-wash p-4 text-[13px] text-coral-ink">
            <AlertTriangle size={15} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="break-words">{cell.error ?? "No figure was produced."}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ComparePage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [tables, setTables] = useState<string[]>([]);
  const [table, setTable] = useState("");
  const [brief, setBrief] = useState("");
  const [plan, setPlan] = useState<ComparisonPlan | null>(null);
  const [cells, setCells] = useState<CellResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? getAccessToken() : null;

  // Restored before anything else, so a reload mid-run does not lose the run.
  const [restored] = useState(() => (typeof window === "undefined" ? null : readCache()));
  useEffect(() => {
    if (!restored) return;
    setPlan(restored.plan);
    setCells(restored.cells);
  }, [restored]);

  useEffect(() => {
    if (!token) return;
    listSources(token)
      .then((rows) => {
        setSources(rows);
        if (rows.length > 0) setSourceId((current) => current || rows[0].id);
      })
      .catch(() => setSources([]));
    listEngines(token).then(setEngines).catch(() => setEngines([]));
  }, [token]);

  // A database source holds many tables; a chart is built from one.
  useEffect(() => {
    if (!token || !sourceId) return;
    const source = sources.find((s) => s.id === sourceId);
    if (source?.source_type !== "db") {
      setTables([]);
      setTable("");
      return;
    }
    listTables(token, sourceId)
      .then((names) => {
        setTables(names);
        setTable((current) => (names.includes(current) ? current : (names[0] ?? "")));
      })
      .catch(() => setTables([]));
  }, [token, sourceId, sources]);

  const opusReady = engines.find((e) => e.id === "opus")?.available ?? false;
  const cost = useMemo(() => opusCost(cells), [cells]);

  async function run() {
    if (!token || !sourceId || running) return;
    setRunning(true);
    setError(null);
    setPlan(null);
    setCells([]);
    let latestPlan: ComparisonPlan | null = null;
    const collected: CellResult[] = [];
    try {
      await runComparison(
        token,
        { sourceId, table: table || undefined, brief },
        {
          onPlan: (incoming) => {
            latestPlan = incoming;
            setPlan(incoming);
          },
          onCell: (cell) => {
            collected.push(cell);
            setCells([...collected]);
            if (latestPlan) writeCache({ plan: latestPlan, cells: collected });
          },
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The comparison could not be run.");
    } finally {
      setRunning(false);
    }
  }


  /* A chart drawn by the deterministic fallback is the harness working, not
     the model. Counting it as a win overstated both sides -- Opus once scored
     5/5 on a run where two of its answers had been rejected. */
  const scored = (engine: Engine) =>
    cells.filter((c) => c.engine === engine && c.ok && !c.used_fallback).length;
  const attempted = (engine: Engine) => cells.filter((c) => c.engine === engine).length;
  const fellBack = (engine: Engine) =>
    cells.filter((c) => c.engine === engine && c.used_fallback).length;

  return (
    <AppShell>
      <PageHeader
        title="Compare models"
        lead="The same question, the same data and the same contract, put to the local fine-tuned model and to Claude Opus 5.5. Only the weights differ."
      />

      <div className="app-scroll px-5 pb-16 sm:px-8">
        <Panel className="mb-5 flex flex-wrap items-end gap-3 p-4">
          <label className="min-w-[13rem] flex-1">
            <span className="mb-1.5 block text-[13px] font-semibold text-ink">Data</span>
            <select
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
              className={inputClass}
            >
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.display_name}
                </option>
              ))}
            </select>
          </label>

          {tables.length > 0 ? (
            <label className="min-w-[11rem] flex-1">
              <span className="mb-1.5 block text-[13px] font-semibold text-ink">Table</span>
              <select
                value={table}
                onChange={(event) => setTable(event.target.value)}
                className={inputClass}
              >
                {tables.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="min-w-[15rem] flex-[2]">
            <span className="mb-1.5 block text-[13px] font-semibold text-ink">
              What should the charts be about?
            </span>
            <input
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void run();
              }}
              placeholder="e.g. life expectancy by continent — optional"
              className={inputClass}
            />
          </label>

          <Button variant="primary" onClick={run} disabled={!sourceId || running || !opusReady}>
            <Sparkles size={15} strokeWidth={2.25} />
            {running ? "Running…" : "Run comparison"}
          </Button>
        </Panel>

        {!opusReady ? (
          <div className="mb-5 flex items-start gap-2 rounded-[var(--r-card)] bg-copper-wash px-4 py-3 text-[13px] text-copper-ink">
            <AlertTriangle size={15} strokeWidth={2.25} className="mt-px shrink-0" />
            <span>
              Claude Opus 5.5 is not configured on the server, so only the local model could run.
              Set <span className="font-mono">CLAUDE_API_KEY</span> and restart the API.
            </span>
          </div>
        ) : null}

        {error ? (
          <div className="mb-5 flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-coral-ink">
            <AlertTriangle size={16} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="flex-1">{error}</span>
          </div>
        ) : null}

        {plan ? (
          <Panel className="mb-5 p-4">
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-body">
              <Chip tone="slate">
                <Database size={11} strokeWidth={2.25} />
                {plan.source}
              </Chip>
              <span className="tabular">{plan.rows.toLocaleString()} rows</span>
              <span>·</span>
              <span className="tabular">{plan.columns.length} columns</span>
              <span>·</span>
              <span className="tabular">{plan.questions.length} questions</span>
              {cells.length > 0 ? (
                <>
                  <span>·</span>
                  <span className="tabular">
                    own code — local {scored("slm")}/{attempted("slm")} · Opus{" "}
                    {scored("opus")}/{attempted("opus")}
                  </span>
                  {fellBack("slm") + fellBack("opus") > 0 ? (
                    <>
                      <span>·</span>
                      <span className="tabular text-[#8a5a00]">
                        fell back — local {fellBack("slm")} · Opus {fellBack("opus")}
                      </span>
                    </>
                  ) : null}
                  <span>·</span>
                  <span className="tabular">Opus spend ${cost.toFixed(3)}</span>
                </>
              ) : null}
            </div>
          </Panel>
        ) : null}

        {!plan && !running ? (
          <Panel>
            <EmptyState
              icon={<Cpu size={20} strokeWidth={2.25} />}
              title="Nothing compared yet"
              body="Pick a data source and run it. Each question is generated twice — once by the model on this machine, once by Claude Opus 5.5 — and both go through the same contract and the same executor."
              action={
                sources.length === 0 ? (
                  <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
                    <FileSpreadsheet size={14} strokeWidth={2.25} />
                    Add a data source first.
                  </span>
                ) : undefined
              }
            />
          </Panel>
        ) : null}

        {plan ? (
          <>
            {plan.intro ? (
              <Panel className="mb-5 p-4">
                <p className="mb-1.5 font-display text-[15px] font-semibold text-ink">
                  {plan.intro_title || "About this data"}
                </p>
                <RichText value={plan.intro} />
                <p className="mt-2 text-[12px] text-muted">
                  Composed from the data profile, not by a model — the same on both sides, so it
                  is shown once.
                </p>
              </Panel>
            ) : null}

            <div className="grid gap-4 xl:grid-cols-2">
              {plan.engines.map((engine) => (
                <section key={engine.id}>
                  <h2 className="mb-2 text-[12.5px] font-bold uppercase tracking-[0.08em] text-muted">
                    {engine.label}
                  </h2>
                  <Dashboard
                    sections={plan.sections}
                    cells={
                      new Map(
                        cells
                          .filter((c) => c.engine === engine.id)
                          .map((c) => [c.index, c] as const),
                      )
                    }
                  />
                </section>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
