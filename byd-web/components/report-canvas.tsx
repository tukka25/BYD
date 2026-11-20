"use client";

import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import {
  AlertTriangle,
  ArrowUp,
  Code2,
  Download,
  Eye,
  GripVertical,
  LayoutGrid,
  Pencil,
  Trash2,
  Type,
} from "lucide-react";
import { Plot } from "@/components/plot";
import { Button, Chip, EmptyState, IconButton, Panel, Segmented, inputClass } from "@/components/ui";
import {
  createBlock,
  deleteBlock,
  generateBlock,
  listBlocks,
  saveLayout,
  updateBlock,
  type Block,
} from "@/lib/blocks";
import { getAccessToken } from "@/lib/auth";
import type { Report } from "@/lib/reports";

const Grid = WidthProvider(Responsive);

const COLS = { lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 };
const BREAKPOINTS = { lg: 1280, md: 996, sm: 768, xs: 480, xxs: 0 };
const ROW_HEIGHT = 44;

type Mode = "view" | "edit";

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
  onDelete,
  onRename,
  children,
}: {
  block: Block;
  mode: Mode;
  onDelete: () => void;
  onRename: (title: string) => void;
  children: React.ReactNode;
}) {
  const [showCode, setShowCode] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <header
        className={[
          "flex items-start gap-2 px-5 pt-4",
          mode === "edit" ? "block-drag cursor-grab active:cursor-grabbing" : "",
        ].join(" ")}
      >
        {mode === "edit" ? (
          <GripVertical size={16} className="mt-0.5 shrink-0 text-hairline-strong" aria-hidden />
        ) : null}

        <div className="min-w-0 flex-1">
          {editingTitle ? (
            <input
              autoFocus
              defaultValue={block.title}
              onBlur={(event) => {
                onRename(event.target.value.trim() || block.title);
                setEditingTitle(false);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") setEditingTitle(false);
              }}
              className="w-full rounded-[8px] bg-sunken px-2 py-1 font-display text-[15px] font-semibold text-ink focus:outline-none focus:ring-2 focus:ring-violet"
            />
          ) : (
            <h3
              className="truncate font-display text-[15px] font-semibold leading-tight text-ink"
              title={block.title}
            >
              {block.title || "Untitled"}
            </h3>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {block.source_name ? (
              <span className="font-mono text-[11px] text-muted">{block.source_name}</span>
            ) : null}
            {block.used_fallback ? (
              <Chip tone="amber">
                <AlertTriangle size={11} strokeWidth={2.5} />
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
              className={showCode ? "bg-violet-wash text-violet" : undefined}
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
      return (
        <textarea
          defaultValue={block.text_body ?? ""}
          placeholder="Write a note, a caption, or what this section shows…"
          onBlur={(event) => onText(event.target.value)}
          className="size-full resize-none rounded-[var(--r-card)] bg-sunken p-4 text-sm leading-relaxed text-body placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-violet"
        />
      );
    }
    return (
      <div className="size-full overflow-auto px-2 py-1 text-sm leading-relaxed text-body">
        {block.text_body?.trim() ? (
          block.text_body.split("\n").map((line, i) => (
            <p key={i} className={line.trim() ? "" : "h-3"}>
              {line}
            </p>
          ))
        ) : (
          <span className="text-muted">Empty note</span>
        )}
      </div>
    );
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
  const askRef = useRef<HTMLTextAreaElement | null>(null);

  const token = typeof window !== "undefined" ? getAccessToken() : null;

  useEffect(() => {
    if (!token) return;
    listBlocks(token, report.id)
      .then(setBlocks)
      .catch(() => setError("Could not load this report's blocks."))
      .finally(() => setLoading(false));
  }, [report.id, token]);

  const layouts = useMemo(
    () => ({
      lg: blocks.map((b) => ({ i: b.id, x: b.x, y: b.y, w: b.w, h: b.h, minW: 2, minH: 3 })),
    }),
    [blocks],
  );

  // react-grid-layout hands back a readonly array, so the parameter matches it
  // rather than copying to satisfy the type.
  type GridItem = { i: string; x: number; y: number; w: number; h: number };
  const persistLayout = useCallback(
    (next: readonly GridItem[]) => {
      if (!token) return;
      setBlocks((current) =>
        current.map((block) => {
          const item = next.find((n) => n.i === block.id);
          return item ? { ...block, x: item.x, y: item.y, w: item.w, h: item.h } : block;
        }),
      );
      saveLayout(
        token,
        report.id,
        next.map((n) => ({ id: n.i, x: n.x, y: n.y, w: n.w, h: n.h })),
      ).catch(() => setError("Layout could not be saved."));
    },
    [report.id, token],
  );

  async function ask() {
    const question = prompt.trim();
    if (!question || !token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const block = await generateBlock(token, report.id, { prompt: question });
      setBlocks((current) => [...current, block]);
      setPrompt("");
      askRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate that chart.");
    } finally {
      setBusy(false);
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
    updateBlock(token, report.id, id, data).catch(() => setError("Could not save that change."));
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex flex-wrap items-center justify-between gap-4 px-5 pb-5 pt-6 sm:px-8 sm:pt-8 print:px-0">
        <div className="min-w-0 basis-full sm:basis-auto">
          <h1 className="font-display text-[26px] font-bold leading-[1.1] text-ink sm:text-[34px]">
            {report.title}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {blocks.length === 0
              ? "Nothing on the canvas yet."
              : `${blocks.length} block${blocks.length === 1 ? "" : "s"}`}
            {report.description ? ` · ${report.description}` : ""}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <Segmented<Mode>
            value={mode}
            onChange={setMode}
            options={[
              { value: "edit", label: "Edit", icon: <LayoutGrid size={14} strokeWidth={2.5} /> },
              { value: "view", label: "View", icon: <Eye size={14} strokeWidth={2.5} /> },
            ]}
          />
          <Button variant="secondary" onClick={addNote}>
            <Type size={15} strokeWidth={2.5} />
            Note
          </Button>
          <Button variant="secondary" onClick={() => window.print()}>
            <Download size={15} strokeWidth={2.5} />
            Export
          </Button>
        </div>
      </header>

      {error ? (
        <div className="mx-5 mb-4 flex items-start sm:mx-8 gap-2 rounded-[var(--r-card)] bg-coral-wash px-4 py-3 text-[13px] text-[#b5301c] print:hidden">
          <AlertTriangle size={16} strokeWidth={2.5} className="mt-px shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} className="font-semibold underline">
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="flex-1 px-2 pb-44 sm:px-5 print:pb-0">
        {loading ? (
          <div className="grid grid-cols-2 gap-4 px-3">
            <div className="h-64 rounded-[var(--r-panel)] generating" />
            <div className="h-64 rounded-[var(--r-panel)] generating" />
          </div>
        ) : blocks.length === 0 ? (
          <Panel className="mx-3">
            <EmptyState
              icon={<ArrowUp size={20} strokeWidth={2.5} />}
              title="Ask a question to start"
              body="Describe the chart you want in plain English — “monthly revenue by plan tier”. It runs against your uploaded data on this machine, and the result lands here as a block you can move and resize."
              action={
                <Button variant="primary" onClick={() => askRef.current?.focus()}>
                  Write a question
                </Button>
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
            isDraggable={mode === "edit"}
            isResizable={mode === "edit"}
            draggableHandle=".block-drag"
            onDragStop={persistLayout}
            onResizeStop={persistLayout}
            compactType="vertical"
          >
            {blocks.map((block) => (
              <div key={block.id}>
                <div className="block-settle h-full">
                  <BlockFrame
                    block={block}
                    mode={mode}
                    onDelete={() => removeBlock(block.id)}
                    onRename={(title) => patch(block.id, { title })}
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

      {/* The primary action. Anchored, not floating over a block: it is how
          every block on this canvas gets made. */}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-4 pb-4 sm:px-8 sm:pb-6 lg:left-[248px] print:hidden">
        <div className="pointer-events-auto mx-auto max-w-3xl">
          <Panel className="shadow-[var(--lift-2)]">
            <div className="flex items-end gap-2 p-2.5">
              <textarea
                ref={askRef}
                rows={1}
                value={prompt}
                disabled={busy}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void ask();
                  }
                }}
                placeholder="Ask for a chart…"
                className={`${inputClass} max-h-32 min-h-11 resize-none py-3 ring-0 focus:ring-0`}
              />
              <Button variant="primary" onClick={ask} disabled={busy || !prompt.trim()} className="shrink-0">
                {busy ? "Working…" : "Add block"}
                {busy ? null : <ArrowUp size={15} strokeWidth={2.75} />}
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
