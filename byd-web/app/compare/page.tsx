"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Code2, Cpu, Database, FileSpreadsheet, Sparkles } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { DotWave } from "@/components/dot-wave";
import { Plot } from "@/components/plot";
import { Button, Chip, EmptyState, Panel, inputClass } from "@/components/ui";
import { getAccessToken } from "@/lib/auth";
import { listSources, type Source } from "@/lib/sources";
import {
  listEngines,
  opusCost,
  runComparison,
  type CellResult,
  type ComparisonPlan,
  type Engine,
  type EngineInfo,
} from "@/lib/comparison";

/* Same question, same data, same contract, same executor — two sets of
   weights. The page exists to make that comparison legible, which means
   showing the failures as plainly as the charts. */

function Cell({ cell }: { cell: CellResult | undefined }) {
  const [showCode, setShowCode] = useState(false);

  if (!cell) {
    return (
      <div className="h-[300px]">
        <DotWave label="Working…" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {cell.ok ? (
          <Chip tone="teal">
            <Check size={11} strokeWidth={3} />
            Rendered
          </Chip>
        ) : (
          <Chip tone="coral">
            <AlertTriangle size={11} strokeWidth={2.25} />
            Failed
          </Chip>
        )}
        {cell.used_fallback ? <Chip tone="amber">Fallback</Chip> : null}
        {cell.violations.length > 0 ? (
          <Chip tone="amber">{cell.violations.join(", ")}</Chip>
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
            className="ml-auto inline-flex items-center gap-1 text-[12px] font-semibold text-violet"
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
          <div className="flex h-[300px] items-start gap-2 rounded-[var(--r-card)] bg-coral-wash p-4 text-[13px] text-[#b5301c]">
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
  const [brief, setBrief] = useState("");
  const [plan, setPlan] = useState<ComparisonPlan | null>(null);
  const [cells, setCells] = useState<CellResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? getAccessToken() : null;

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

  const opusReady = engines.find((e) => e.id === "opus")?.available ?? false;
  const cost = useMemo(() => opusCost(cells), [cells]);

  async function run() {
    if (!token || !sourceId || running) return;
    setRunning(true);
    setError(null);
    setPlan(null);
    setCells([]);
    try {
      await runComparison(
        token,
        { sourceId, brief },
        {
          onPlan: setPlan,
          onCell: (cell) => setCells((current) => [...current, cell]),
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The comparison could not be run.");
    } finally {
      setRunning(false);
    }
  }

  const cellFor = (index: number, engine: Engine) =>
    cells.find((c) => c.index === index && c.engine === engine);

  const scored = (engine: Engine) => cells.filter((c) => c.engine === engine && c.ok).length;
  const attempted = (engine: Engine) => cells.filter((c) => c.engine === engine).length;

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
          <div className="mb-5 flex items-start gap-2 rounded-[var(--r-card)] bg-amber-wash px-4 py-3 text-[13px] text-[#8a5a00]">
            <AlertTriangle size={15} strokeWidth={2.25} className="mt-px shrink-0" />
            <span>
              Claude Opus 5.5 is not configured on the server, so only the local model could run.
              Set <span className="font-mono">CLAUDE_API_KEY</span> and restart the API.
            </span>
          </div>
        ) : null}

        {error ? (
          <div className="mb-5 flex items-start gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-[#b5301c]">
            <AlertTriangle size={16} strokeWidth={2.25} className="mt-px shrink-0" />
            <span className="flex-1">{error}</span>
          </div>
        ) : null}

        {plan ? (
          <Panel className="mb-5 p-4">
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-body">
              <Chip tone="violet">
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
                    local {scored("slm")}/{attempted("slm")} · Opus {scored("opus")}/
                    {attempted("opus")}
                  </span>
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

        {plan
          ? plan.questions.map((question, index) => (
              <div key={question} className="mb-5">
                <p className="mb-2 font-display text-[15px] font-semibold text-ink">
                  {index + 1}. {question}
                </p>
                <div className="grid gap-4 lg:grid-cols-2">
                  {plan.engines.map((engine) => (
                    <Panel key={engine.id} className="p-4">
                      <p className="mb-2 text-[12.5px] font-bold uppercase tracking-[0.08em] text-muted">
                        {engine.label}
                      </p>
                      <Cell cell={cellFor(index, engine.id)} />
                    </Panel>
                  ))}
                </div>
              </div>
            ))
          : null}
      </div>
    </AppShell>
  );
}
