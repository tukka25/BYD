"use client";

import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import {
  AlertTriangle,
  ArrowUp,
  ChevronDown,
  Code2,
  Database,
  Download,
  Eye,
  GripVertical,
  LayoutGrid,
  Pencil,
  Save,
  Sparkles,
  Trash2,
  Type,
} from "lucide-react";
import { DotWave } from "@/components/dot-wave";
import { KindChip, KindMenu, useKindMenu } from "@/components/kind-menu";
import { Plot } from "@/components/plot";
import { RichText, RichTextEditor } from "@/components/rich-text";
import type { ChartKind } from "@/lib/chart-kinds";
import { exportReportToPdf } from "@/lib/export-pdf";
import { SourceDialog } from "@/components/sources";
import { Button, Chip, EmptyState, IconButton, Panel, Segmented, inputClass } from "@/components/ui";
import {
  createBlock,
  deleteBlock,
  generateBlock,
  generateDashboard,
  type PlannedSection,
  listBlocks,
  saveLayout,
  updateBlock,
  type Block,
} from "@/lib/blocks";
import { getAccessToken } from "@/lib/auth";
import { listSources } from "@/lib/sources";
import { updateReport, type Report } from "@/lib/reports";

const Grid = WidthProvider(Responsive);

/* These thresholds are CONTAINER widths, not viewport widths: `WidthProvider`
   measures the element it wraps, and the canvas sits inside a 248px sidebar
   plus its own padding. Reading them as viewport widths is how a 1280px laptop
   silently lands on a 6-column grid and writes that back as the layout. */
const BREAKPOINTS = { lg: 900, md: 700, sm: 540, xs: 400, xxs: 0 };
const COLS = { lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 };
const ROW_HEIGHT = 44;
const STORED_COLS = 12;

function columnsFor(width: number): number {
  if (width >= BREAKPOINTS.lg) return COLS.lg;
  if (width >= BREAKPOINTS.md) return COLS.md;
  if (width >= BREAKPOINTS.sm) return COLS.sm;
  if (width >= BREAKPOINTS.xs) return COLS.xs;
  return COLS.xxs;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

type Nudge = { dx?: number; dy?: number; dw?: number; dh?: number };

type Mode = "view" | "edit";

/* Everything on this canvas writes as you go. The indicator exists so that is
   visible rather than assumed, and the Save button is the explicit version of
   the same write for anyone who would rather press something. */
type SaveState = "idle" | "saving" | "saved" | "error";

/* The pipeline's real stages, with the durations they were measured at
   (planner 1.6s, detective effectively instant, chartist 13.3s). The label
   advances on that schedule because the server answers once at the end and
   cannot report a stage; no percentage is shown for a single block, because
   there is no real number to show. */
const PHASES: Array<{ at: number; label: string }> = [
  { at: 0, label: "Choosing the chart" },
  { at: 1.6, label: "Finding the data" },
  { at: 2.2, label: "Writing the code" },
  { at: 15, label: "Running it on your data" },
];

type Building = { done: number; total: number; label: string };

const PLACEHOLDER_PREFIX = "__planned_";
const SINGLE_PLACEHOLDER = "__planned_single__";

/* A Plotly `indicator` trace is already a metric card: one big number, no axes.
   The chartist was fine-tuned on that chart type, so a KPI can come back as a
   figure rather than needing a separate block kind. Detected here so it is
   drawn without plot chrome. */
function isIndicator(block: Block): boolean {
  const data = (block.figure?.data as Array<{ type?: string }> | undefined) ?? [];
  return data.length > 0 && data.every((trace) => trace?.type === "indicator");
}

function BlockFrame({
  block,
  mode,
  arrangeable,
  onDelete,
  onRename,
  onNudge,
  children,
}: {
  block: Block;
  mode: Mode;
  arrangeable: boolean;
  onDelete: () => void;
  onRename: (title: string) => void;
  onNudge: (nudge: Nudge) => void;
  children: React.ReactNode;
}) {
  const [showCode, setShowCode] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const grabbable = mode === "edit" && arrangeable;

  /* The drag handle is a keyboard control too: arrows move the block, shift
     and arrows resize it, both writing through the same save path as a drag.
     Without this the canvas can only be arranged with a mouse, which PRODUCT.md
     names as a requirement rather than a nicety. */
  function onKeyDown(event: React.KeyboardEvent) {
    if (!grabbable) return;
    const sizing = event.shiftKey;
    const map: Record<string, Nudge> = {
      ArrowLeft: sizing ? { dw: -1 } : { dx: -1 },
      ArrowRight: sizing ? { dw: 1 } : { dx: 1 },
      ArrowUp: sizing ? { dh: -1 } : { dy: -1 },
      ArrowDown: sizing ? { dh: 1 } : { dy: 1 },
    };
    const next = map[event.key];
    if (!next) return;
    event.preventDefault();
    onNudge(next);
  }

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <header
        tabIndex={grabbable ? 0 : undefined}
        role={grabbable ? "button" : undefined}
        aria-label={
          grabbable
            ? `${block.title || "Untitled"}. Arrow keys move this block, shift and arrow keys resize it.`
            : undefined
        }
        onKeyDown={onKeyDown}
        className={[
          "flex items-start gap-2 rounded-t-[var(--r-panel)] px-5 pt-4",
          grabbable ? "block-drag cursor-grab active:cursor-grabbing" : "",
        ].join(" ")}
      >
        {grabbable ? (
          <GripVertical size={16} className="mt-0.5 shrink-0 text-hairline-strong" aria-hidden />
        ) : null}

        <div className="min-w-0 flex-1">
          {editingTitle ? (
            <input
              autoFocus
              defaultValue={block.title}
              aria-label="Block title"
              onBlur={(event) => {
                onRename(event.target.value.trim() || block.title);
                setEditingTitle(false);
              }}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") setEditingTitle(false);
              }}
              className="w-full rounded-[8px] bg-sunken px-2 py-1 font-display text-[15px] font-semibold text-ink focus:outline-none focus:ring-2 focus:ring-pine"
            />
          ) : (
            <h3
              className="truncate font-display text-[15px] font-semibold leading-tight text-ink"
              title={block.title}
            >
              {block.title || "Untitled"}
            </h3>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1.5 empty:mt-0">
            {block.used_fallback ? (
              <Chip tone="copper">
                <AlertTriangle size={11} strokeWidth={2.25} />
                Fallback chart
              </Chip>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 items-center">
          {block.code ? (
            <IconButton
              label={showCode ? "Hide the code" : "Show the code that drew this"}
              onClick={() => setShowCode((v) => !v)}
              className={showCode ? "bg-pine-wash text-pine" : undefined}
            >
              <Code2 size={15} strokeWidth={2.25} />
            </IconButton>
          ) : null}
          {mode === "edit" ? (
            <>
              <IconButton label="Rename block" onClick={() => setEditingTitle(true)}>
                <Pencil size={15} strokeWidth={2.25} />
              </IconButton>
              <IconButton label="Delete block" tone="danger" onClick={onDelete}>
                <Trash2 size={15} strokeWidth={2.25} />
              </IconButton>
            </>
          ) : null}
        </div>
      </header>

      <div className="min-h-0 flex-1 px-3 pb-3 pt-2">
        {showCode && block.code ? (
          <pre className="size-full overflow-auto rounded-[var(--r-card)] bg-inverse p-4 font-mono text-[11.5px] leading-relaxed text-on-dark">
            <code>{block.code}</code>
          </pre>
        ) : (
          children
        )}
      </div>
    </Panel>
  );
}

function BlockBody({
  block,
  mode,
  onText,
}: {
  block: Block;
  mode: Mode;
  onText: (text: string) => void;
}) {
  if (block.kind === "text") {
    if (mode === "edit") {
      return <RichTextEditor value={block.text_body} onCommit={onText} />;
    }
    return <RichText value={block.text_body} />;
  }

  if (!block.figure) {
    return (
      <div className="grid size-full place-items-center text-[13px] text-muted">
        No figure stored for this block.
      </div>
    );
  }

  return <Plot figure={block.figure} className={isIndicator(block) ? "[&_.cartesianlayer]:hidden" : ""} />;
}

export function ReportCanvas({ report }: { report: Report }) {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [mode, setMode] = useState<Mode>("edit");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourceNames, setSourceNames] = useState<string[]>([]);
  const [cols, setCols] = useState(STORED_COLS);
  const [announcement, setAnnouncement] = useState("");
  const [askFocused, setAskFocused] = useState(false);
  const [title, setTitle] = useState(report.title);
  const [draftTitle, setDraftTitle] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [sourceIds, setSourceIds] = useState<string[]>(report.dataSourceIds);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [building, setBuilding] = useState<Building | null>(null);
  const [planned, setPlanned] = useState<PlannedSection[]>([]);
  const [running, setRunning] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);
  const [askKind, setAskKind] = useState<ChartKind | null>(null);
  const [briefKinds, setBriefKinds] = useState<ChartKind[]>([]);
  const askMenu = useKindMenu((picked, next) => {
    setAskKind(picked);
    setPrompt(next.text);
    requestAnimationFrame(() => askRef.current?.setSelectionRange(next.caret, next.caret));
  });
  const briefMenu = useKindMenu((picked, next) => {
    setBriefKinds((current) =>
      current.some((k) => k.kind === picked.kind) ? current : [...current, picked].slice(0, 4),
    );
    setBrief(next.text);
  });
  const [brief, setBrief] = useState("");
  const [skipped, setSkipped] = useState<string[]>([]);
  const [phase, setPhase] = useState(PHASES[0].label);
  const askRef = useRef<HTMLTextAreaElement | null>(null);
  const gridHost = useRef<HTMLDivElement | null>(null);

  const token = typeof window !== "undefined" ? getAccessToken() : null;

  /* The stored layout is in 12 columns. At a narrower breakpoint the grid
     clamps every block to fit, so writing that back would permanently squash a
     report arranged on a wide screen. Arranging is therefore only offered
     where the grid still has all 12 columns. */
  const arrangeable = cols === STORED_COLS;

  useEffect(() => {
    if (!token) return;
    listBlocks(token, report.id)
      .then(setBlocks)
      .catch(() => setError("Could not load this report's blocks."))
      .finally(() => setLoading(false));
  }, [report.id, token]);

  useEffect(() => {
    if (!token || sourceIds.length === 0) {
      setSourceNames([]);
      return;
    }
    listSources(token)
      .then((all) => setSourceNames(all.filter((s) => sourceIds.includes(s.id)).map((s) => s.display_name)))
      .catch(() => setSourceNames([]));
  }, [sourceIds, token]);

  // Measured here rather than taken from the grid's own breakpoint callback,
  // which only fires on a change and so can leave the first render wrong.
  useEffect(() => {
    const node = gridHost.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      setCols(columnsFor(entry.contentRect.width));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = (Date.now() - started) / 1000;
      const current = [...PHASES].reverse().find((p) => elapsed >= p.at) ?? PHASES[0];
      setPhase(current.label);
    }, 400);
    return () => window.clearInterval(timer);
  }, [busy]);

  const nextRow = useMemo(
    () => blocks.reduce((low, b) => Math.max(low, b.y + b.h), 0),
    [blocks],
  );

  /* A placeholder sits where its block will land, so one click lays the whole
     dashboard out and each tile fills itself in. */
  const placeholders = useMemo(() => {
    if (planned.length > 0) {
      return planned.map((s) => ({
        key: `${PLACEHOLDER_PREFIX}${s.index}__`,
        label: s.label,
        index: s.index,
        x: s.x,
        y: s.y,
        w: s.w,
        h: s.h,
      }));
    }
    if (busy) {
      return [
        { key: SINGLE_PLACEHOLDER, label: phase, index: -1, x: 0, y: nextRow, w: 6, h: 9 },
      ];
    }
    return [];
  }, [planned, busy, phase, nextRow]);

  const layouts = useMemo(
    () => ({
      lg: [
        ...blocks.map((b) => ({ i: b.id, x: b.x, y: b.y, w: b.w, h: b.h, minW: 2, minH: 3 })),
        ...placeholders.map((p) => ({
          i: p.key,
          x: p.x,
          y: p.y,
          w: p.w,
          h: p.h,
          static: true,
        })),
      ],
    }),
    [blocks, placeholders],
  );

  // react-grid-layout hands back a readonly array, so the parameter matches it
  // rather than copying to satisfy the type.
  type GridItem = { i: string; x: number; y: number; w: number; h: number };

  const track = useCallback(async <T,>(write: () => Promise<T>): Promise<T | null> => {
    setSaveState("saving");
    try {
      const result = await write();
      setSaveState("saved");
      setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      return result;
    } catch {
      setSaveState("error");
      return null;
    }
  }, []);

  const save = useCallback(
    (next: Array<{ id: string; x: number; y: number; w: number; h: number }>) => {
      if (!token) return;
      void track(() => saveLayout(token, report.id, next)).then((ok) => {
        if (ok === null) setError("Layout could not be saved.");
      });
    },
    [report.id, token, track],
  );

  async function commitTitle(next: string) {
    const clean = next.trim();
    setEditingTitle(false);
    if (!token || !clean || clean === title) return;
    setTitle(clean);
    const saved = await track(() => updateReport(token, report.id, { title: clean }));
    if (saved === null) {
      setTitle(report.title);
      setError("The report name could not be saved.");
    }
  }

  /* The explicit Save: commit whatever is being edited right now (a note, the
     title), then write the layout. It is a real write, not a reassurance. */
  async function saveNow() {
    const focused = document.activeElement;
    if (focused instanceof HTMLElement) focused.blur();
    if (!token) return;
    await track(async () => {
      await updateReport(token, report.id, { title });
      if (blocks.length > 0) {
        await saveLayout(
          token,
          report.id,
          blocks.map((b) => ({ id: b.id, x: b.x, y: b.y, w: b.w, h: b.h })),
        );
      }
    });
  }

  /* Export is the app's own document now, not the browser's print dialog.
     The charts are re-rendered by Plotly at their printed size, which takes a
     moment on a full dashboard, so the button says so rather than appearing
     to have done nothing. */
  async function runExport() {
    if (exporting || blocks.length === 0) return;
    setExporting(true);
    setError(null);
    try {
      const result = await exportReportToPdf({
        title: title || "Report",
        sources: sourceNames,
        blocks,
      });
      setAnnouncement(
        `Exported ${result.blocks} blocks to ${result.filename}, ${result.pages} pages.`,
      );
      if (result.chartsFailed > 0) {
        setError(
          result.chartsFailed === 1
            ? "One chart could not be drawn and is marked in the PDF."
            : `${result.chartsFailed} charts could not be drawn and are marked in the PDF.`,
        );
      }
    } catch {
      setError("Could not build the PDF.");
    } finally {
      setExporting(false);
    }
  }

  const persistLayout = useCallback(
    (next: readonly GridItem[]) => {
      // Never write back a layout the grid clamped to fit a narrow screen.
      if (!arrangeable) return;
      const real = next.filter((n) => !n.i.startsWith(PLACEHOLDER_PREFIX));
      setBlocks((current) =>
        current.map((block) => {
          const item = real.find((n) => n.i === block.id);
          return item ? { ...block, x: item.x, y: item.y, w: item.w, h: item.h } : block;
        }),
      );
      save(real.map((n) => ({ id: n.i, x: n.x, y: n.y, w: n.w, h: n.h })));
    },
    [arrangeable, save],
  );

  function nudge(id: string, by: Nudge) {
    if (!arrangeable) return;
    const target = blocks.find((b) => b.id === id);
    if (!target) return;

    const w = clamp(target.w + (by.dw ?? 0), 2, STORED_COLS);
    const h = Math.max(3, target.h + (by.dh ?? 0));
    const x = clamp(target.x + (by.dx ?? 0), 0, STORED_COLS - w);
    const y = Math.max(0, target.y + (by.dy ?? 0));

    const next = blocks.map((b) => (b.id === id ? { ...b, x, y, w, h } : b));
    setBlocks(next);
    save(next.map((b) => ({ id: b.id, x: b.x, y: b.y, w: b.w, h: b.h })));
    setAnnouncement(
      by.dw || by.dh
        ? `${target.title || "Block"} resized to ${w} by ${h}`
        : `${target.title || "Block"} moved to column ${x + 1}, row ${y + 1}`,
    );
  }

  async function ask() {
    const question = prompt.trim();
    if (!question || !token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const block = await generateBlock(token, report.id, { prompt: question, chartKind: askKind?.kind });
      setBlocks((current) => [...current, block]);
      setPrompt("");
      setAskKind(null);
      askRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate that chart.");
    } finally {
      setBusy(false);
    }
  }

  /* Plans a dashboard from the data and builds it block by block. The blocks
     land on the canvas as they are finished rather than all at the end, so
     what is on screen is always what exists. */
  async function buildDashboard() {
    if (!token || building || busy) return;
    setBriefOpen(false);
    setSkipped([]);
    setError(null);
    setPlanned([]);
    setRunning(null);
    setBuilding({ done: 0, total: 0, label: "Reading the data" });
    let completed = 0;
    // Tracked here, not read from state: the handlers below close over the
    // render that started the build, where `running` is still null.
    let currentIndex = -1;
    try {
      await generateDashboard(token, report.id, { brief, chartKinds: briefKinds.map((k) => k.kind) }, {
        // The analyst and planner run before there is a plan to count.
        onStatus: (status) => setBuilding({ done: 0, total: 0, label: status.label }),
        onPlan: (plan) => {
          setPlanned(plan.sections);
          setBuilding({ done: 0, total: plan.total, label: plan.source });
        },
        onStep: (step) => {
          currentIndex = step.index;
          setRunning(step.index);
          setBuilding({ done: completed, total: step.total, label: step.label });
        },
        onBlock: (block) => {
          completed += 1;
          setBlocks((current) => [...current, block]);
          setPlanned((current) => current.filter((s) => s.index !== currentIndex));
          setBuilding((current) => (current ? { ...current, done: completed } : current));
        },
        onSkipped: (skip) => {
          completed += 1;
          setSkipped((current) => [...current, skip.label]);
          setPlanned((current) => current.filter((s) => s.index !== skip.index));
          setBuilding((current) => (current ? { ...current, done: completed } : current));
        },
      });
      setSaveState("saved");
      setBriefKinds([]);
      setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build that dashboard.");
    } finally {
      setBuilding(null);
      setPlanned([]);
      setRunning(null);
    }
  }

  async function addNote() {
    if (!token) return;
    const block = await createBlock(token, report.id, { kind: "text", title: "Note" });
    setBlocks((current) => [...current, block]);
    setMode("edit");
  }

  async function removeBlock(id: string) {
    if (!token) return;
    setBlocks((current) => current.filter((b) => b.id !== id));
    deleteBlock(token, report.id, id).catch(() => setError("Could not delete that block."));
  }

  async function patch(id: string, data: Partial<Block>) {
    if (!token) return;
    setBlocks((current) => current.map((b) => (b.id === id ? { ...b, ...data } : b)));
    const saved = await track(() => updateBlock(token, report.id, id, data));
    if (saved === null) setError("Could not save that change.");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 px-5 pb-5 pt-6 sm:px-8 sm:pt-8 print:px-0">
        <div className="min-w-0 basis-full sm:basis-auto">
          {editingTitle ? (
            <input
              autoFocus
              aria-label="Report name"
              value={draftTitle}
              // Renaming starts with the old name selected, so typing replaces
              // it instead of running on from the end of it.
              onFocus={(event) => event.currentTarget.select()}
              onChange={(event) => setDraftTitle(event.target.value)}
              onBlur={(event) => void commitTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                // Escape unmounts the field, so no blur fires and nothing is
                // written: the name goes back to what it was.
                if (event.key === "Escape") setEditingTitle(false);
              }}
              className="w-full max-w-xl rounded-[var(--r-control)] bg-surface px-2.5 py-0.5 font-display text-[26px] font-bold leading-[1.1] text-ink ring-1 ring-inset ring-hairline focus:outline-none focus:ring-2 focus:ring-pine sm:text-[34px]"
            />
          ) : (
            <button
              type="button"
              title="Rename this report"
              onClick={() => {
                setDraftTitle(title);
                setEditingTitle(true);
              }}
              className="group flex max-w-full items-center gap-2 rounded-[var(--r-control)] text-left"
            >
              <h1 className="truncate font-display text-[26px] font-bold leading-[1.1] text-ink sm:text-[34px]">
                {title}
              </h1>
              <Pencil
                size={16}
                strokeWidth={2.25}
                aria-hidden
                className="shrink-0 text-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
              />
            </button>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSourcesOpen(true)}
              title="Choose what this report can read"
              className="rounded-[var(--r-pill)] transition-opacity duration-150 hover:opacity-80"
            >
              <Chip tone={sourceNames.length > 0 ? "slate" : "neutral"}>
                <Database size={11} strokeWidth={2.25} />
                {sourceNames.length > 0 ? sourceNames.join(", ") : "Any source"}
                <ChevronDown size={11} strokeWidth={2.75} aria-hidden />
              </Chip>
            </button>
            <span className="text-sm text-muted">
              {blocks.length === 0
                ? "Nothing on the canvas yet."
                : `${blocks.length} block${blocks.length === 1 ? "" : "s"}`}
              {report.description ? ` · ${report.description}` : ""}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <Segmented<Mode>
            value={mode}
            onChange={setMode}
            options={[
              { value: "edit", label: "Edit", icon: <LayoutGrid size={14} strokeWidth={2.25} /> },
              { value: "view", label: "View", icon: <Eye size={14} strokeWidth={2.25} /> },
            ]}
          />
          <Button
            variant="primary"
            onClick={() => (building ? undefined : setBriefOpen((v) => !v))}
            disabled={Boolean(building) || busy}
          >
            <Sparkles size={15} strokeWidth={2.25} />
            {building
              ? building.total > 0
                ? `Building ${building.done}/${building.total}`
                : `${building.label}…`
              : "Generate dashboard"}
          </Button>
          <Button variant="secondary" onClick={addNote}>
            <Type size={15} strokeWidth={2.25} />
            Note
          </Button>
          <Button variant="secondary" onClick={saveNow} disabled={saveState === "saving"}>
            <Save size={15} strokeWidth={2.25} />
            Save
          </Button>
          <Button variant="secondary" onClick={runExport} disabled={exporting || blocks.length === 0}>
            <Download size={15} strokeWidth={2.25} />
            {exporting ? "Exporting…" : "Export"}
          </Button>
        </div>

        <p
          aria-live="polite"
          className={[
            "basis-full text-[12.5px] print:hidden",
            saveState === "error" ? "text-coral-ink" : "text-muted",
          ].join(" ")}
        >
          {saveState === "saving"
            ? "Saving…"
            : saveState === "error"
              ? "Last change could not be saved."
              : saveState === "saved"
                ? `All changes saved${savedAt ? ` · ${savedAt}` : ""}`
                : "Changes save as you make them."}
        </p>
      </header>

      {briefOpen && !building ? (
        <div className="shrink-0 px-5 pb-4 sm:px-8 print:hidden">
          <Panel className="flex flex-wrap items-end gap-2 p-3">
            <div className="relative min-w-[14rem] flex-1">
              <label htmlFor="brief-input" className="mb-1.5 block text-[13px] font-semibold text-ink">
                What should this dashboard be about?
              </label>
              {briefKinds.length ? (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {briefKinds.map((k) => (
                    <KindChip
                      key={k.kind}
                      kind={k}
                      onRemove={() => setBriefKinds((current) => current.filter((c) => c.kind !== k.kind))}
                    />
                  ))}
                </div>
              ) : null}
              <input
                id="brief-input"
                autoFocus
                value={brief}
                role="combobox"
                aria-expanded={briefMenu.open}
                aria-controls="brief-kinds"
                aria-autocomplete="list"
                aria-activedescendant={briefMenu.active ? `brief-kinds-${briefMenu.active.kind}` : undefined}
                onChange={(event) => {
                  setBrief(event.target.value);
                  briefMenu.sync(event.target.value, event.target.selectionStart ?? event.target.value.length);
                }}
                onBlur={briefMenu.close}
                onKeyDown={(event) => {
                  if (briefMenu.keyDown(event, brief)) return;
                  if (event.key === "Enter") void buildDashboard();
                  if (event.key === "Escape") setBriefOpen(false);
                }}
                placeholder="e.g. churn by region — type / to ask for a chart kind"
                className={inputClass}
              />
              {briefMenu.open ? (
                <KindMenu
                  id="brief-kinds"
                  options={briefMenu.options}
                  active={briefMenu.active}
                  onPick={(k) => briefMenu.pick(brief, k)}
                  onHighlight={briefMenu.highlight}
                  placement="below"
                />
              ) : null}
            </div>
            <Button variant="primary" onClick={buildDashboard}>
              <Sparkles size={15} strokeWidth={2.25} />
              Build it
            </Button>
            <Button variant="ghost" onClick={() => setBriefOpen(false)}>
              Cancel
            </Button>
          </Panel>
        </div>
      ) : null}

      {error ? (
        <div className="mx-5 mb-4 flex shrink-0 items-start gap-2 sm:mx-8 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-coral-ink print:hidden">
          <AlertTriangle size={16} strokeWidth={2.25} className="mt-px shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} className="font-semibold underline">
            Dismiss
          </button>
        </div>
      ) : null}

      {mode === "edit" && !arrangeable && blocks.length > 0 ? (
        <p className="mx-5 mb-3 shrink-0 text-[12.5px] text-muted sm:mx-8 print:hidden">
          This window is too narrow to arrange blocks — they are stacked to fit. Widen it to move
          and resize them; the layout you saved is kept.
        </p>
      ) : null}

      <div ref={gridHost} className="app-scroll px-2 pb-6 sm:px-5">
        {skipped.length > 0 ? (
          <p className="mb-3 px-3 text-[12.5px] text-muted">
            {skipped.length} block{skipped.length === 1 ? "" : "s"} could not be drawn and
            {skipped.length === 1 ? " was" : " were"} left out: {skipped.join(", ")}
          </p>
        ) : null}

        {loading ? (
          <div className="grid grid-cols-2 gap-4 px-3">
            <div className="h-64 rounded-[var(--r-panel)] generating" />
            <div className="h-64 rounded-[var(--r-panel)] generating" />
          </div>
        ) : blocks.length === 0 && placeholders.length === 0 ? (
          <Panel className="mx-3">
            <EmptyState
              icon={<ArrowUp size={20} strokeWidth={2.25} />}
              title="Ask a question to start"
              body="Describe the chart you want in plain English — “monthly revenue by plan tier”. It runs against your uploaded data on this machine, and the result lands here as a block you can move and resize."
              action={
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <Button
                    variant="primary"
                    onClick={() => setBriefOpen(true)}
                    disabled={Boolean(building)}
                  >
                    <Sparkles size={15} strokeWidth={2.25} />
                    Generate a dashboard
                  </Button>
                  <Button variant="secondary" onClick={() => askRef.current?.focus()}>
                    Write a question
                  </Button>
                </div>
              }
            />
          </Panel>
        ) : (
          <Grid
            className="layout"
            layouts={layouts}
            breakpoints={BREAKPOINTS}
            cols={COLS}
            rowHeight={ROW_HEIGHT}
            margin={[16, 16]}
            isDraggable={mode === "edit" && arrangeable}
            isResizable={mode === "edit" && arrangeable}
            draggableHandle=".block-drag"
            onDragStop={persistLayout}
            onResizeStop={persistLayout}
            compactType="vertical"
          >
            {placeholders.map((placeholder) => (
              <div key={placeholder.key}>
                <Panel className="h-full p-2">
                  <DotWave
                    label={placeholder.label}
                    percent={
                      building && building.total > 0 && placeholder.index === running
                        ? (building.done / building.total) * 100
                        : null
                    }
                  />
                </Panel>
              </div>
            ))}

            {blocks.map((block) => (
              /* data-block-id is how lib/export-pdf.ts finds this block's
                 Plotly graph div to re-render it into the PDF. */
              <div key={block.id} data-block-id={block.id}>
                <div className="block-settle h-full">
                  <BlockFrame
                    block={block}
                    mode={mode}
                    arrangeable={arrangeable}
                    onDelete={() => removeBlock(block.id)}
                    onRename={(title) => patch(block.id, { title })}
                    onNudge={(by) => nudge(block.id, by)}
                  >
                    <BlockBody
                      block={block}
                      mode={mode}
                      onText={(text_body) => patch(block.id, { text_body })}
                    />
                  </BlockFrame>
                </div>
              </div>
            ))}
          </Grid>
        )}
      </div>

      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {sourcesOpen && token ? (
        <SourceDialog
          token={token}
          selected={sourceIds}
          onClose={() => setSourcesOpen(false)}
          onSave={(ids) => {
            setSourceIds(ids);
            setSourcesOpen(false);
            void track(() => updateReport(token, report.id, { dataSourceIds: ids })).then((ok) => {
              if (ok === null) setError("That choice of data could not be saved.");
            });
          }}
        />
      ) : null}

      {/* The primary action, at the foot of the canvas rather than floating
          over it: the grid scrolls above it, so no block ever passes
          underneath. It is how every block on this canvas gets made. */}
      <div className="shrink-0 px-4 pb-4 sm:px-8 sm:pb-6 print:hidden">
        <div className="mx-auto max-w-3xl">
          <Panel
            className={[
              "shadow-[var(--lift-2)] transition-shadow",
              askFocused ? "ring-2 ring-pine" : "",
            ].join(" ")}
          >
            {askKind ? (
              <div className="flex items-center gap-2 px-3 pt-2.5">
                <KindChip kind={askKind} onRemove={() => setAskKind(null)} />
                <span className="text-[12px] text-muted">
                  The model will draw this as a {askKind.label.toLowerCase()}.
                </span>
              </div>
            ) : null}
            <div className="relative flex items-end gap-2 p-2.5">
              {askMenu.open ? (
                <KindMenu
                  id="ask-kinds"
                  options={askMenu.options}
                  active={askMenu.active}
                  onPick={(k) => askMenu.pick(prompt, k)}
                  onHighlight={askMenu.highlight}
                />
              ) : null}
              <textarea
                ref={askRef}
                rows={1}
                value={prompt}
                disabled={busy}
                aria-label="Ask for a chart"
                role="combobox"
                aria-expanded={askMenu.open}
                aria-controls="ask-kinds"
                aria-autocomplete="list"
                aria-activedescendant={askMenu.active ? `ask-kinds-${askMenu.active.kind}` : undefined}
                onFocus={() => setAskFocused(true)}
                onBlur={() => {
                  setAskFocused(false);
                  askMenu.close();
                }}
                onChange={(event) => {
                  setPrompt(event.target.value);
                  askMenu.sync(event.target.value, event.target.selectionStart ?? event.target.value.length);
                }}
                onKeyDown={(event) => {
                  if (askMenu.keyDown(event, prompt)) return;
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void ask();
                  }
                }}
                placeholder="Ask for a chart… type / to pick a chart kind"
                className="max-h-32 min-h-11 w-full resize-none rounded-[var(--r-control)] bg-surface px-3.5 py-3 text-sm text-ink placeholder:text-muted focus:outline-none"
              />
              <Button variant="primary" onClick={ask} disabled={busy || !prompt.trim()} className="shrink-0">
                {busy ? "Working…" : "Add block"}
                {busy ? null : <ArrowUp size={15} strokeWidth={2.25} />}
              </Button>
            </div>
            {busy ? (
              <div className="px-2.5 pb-2.5">
                <div className="h-1.5 w-full overflow-hidden rounded-full generating" />
                <p className="mt-2 px-1 text-[12px] text-muted">
                  Running the model on this machine. Chart generation takes about 15 seconds.
                </p>
              </div>
            ) : null}
          </Panel>
        </div>
      </div>
    </div>
  );
}
