"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { Plot } from "@/components/plot";
import { IconButton } from "@/components/ui";
import { CHART_KINDS, loadKindExamples, type ChartKind, type KindExample } from "@/lib/chart-kinds";

/* What the examples file gave: nothing yet, the charts in it, or why it did not load. */
type Examples =
  | { status: "loading" }
  | { status: "loaded"; byKind: Record<string, KindExample> }
  | { status: "failed"; reason: string };

/* The chart kinds the model can draw, from the fixed list in lib/chart-kinds.ts.
   Each thumbnail is a real chart the model drew from sample data
   (backend/scripts/make_chart_kind_examples.py). A kind missing from the file
   says "No example yet" rather than showing a stand-in. A file that did not
   load says so, with the reason, in place of the thumbnails: "No example yet"
   on every kind would be false. */
export function ChartKindsPanel({
  onClose,
  onUse,
}: {
  onClose: () => void;
  onUse: (kind: ChartKind) => void;
}) {
  const [examples, setExamples] = useState<Examples>({ status: "loading" });

  useEffect(() => {
    let live = true;
    loadKindExamples()
      .then((byKind) => {
        if (live) setExamples({ status: "loaded", byKind });
      })
      .catch((error: unknown) => {
        if (live) setExamples({ status: "failed", reason: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label="Chart kinds"
      className="fixed inset-y-0 right-0 z-40 flex w-[min(380px,100vw)] flex-col bg-surface shadow-[var(--lift-2)] print:hidden"
    >
      <header className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">Chart kinds</h2>
          <p className="mt-0.5 text-[12.5px] text-muted">
            What the model can draw. Pick one here, or type / in the ask bar.
          </p>
        </div>
        <IconButton label="Close chart kinds" onClick={onClose}>
          <X size={16} strokeWidth={2.25} />
        </IconButton>
      </header>
      {examples.status === "failed" ? (
        <p
          role="alert"
          className="mx-5 mb-3 flex items-start gap-2 rounded-[var(--r-control)] bg-coral-wash px-3 py-2.5 text-[12.5px] text-coral-ink"
        >
          <AlertTriangle size={14} strokeWidth={2.25} className="mt-px shrink-0" />
          <span className="break-words">Could not load the examples ({examples.reason}).</span>
        </p>
      ) : null}
      <ul className="app-scroll flex-1 space-y-1.5 px-3 pb-5">
        {CHART_KINDS.map((kind) => {
          const example = examples.status === "loaded" ? examples.byKind[kind.kind] : undefined;
          return (
            <li key={kind.kind}>
              <button
                type="button"
                onClick={() => onUse(kind)}
                className="flex w-full items-center gap-3 rounded-[var(--r-card)] p-2 text-left transition-colors hover:bg-sunken"
              >
                {/* A failed load shows one line above the list, not a box per kind;
                    while loading, the box is a skeleton, never "No example yet". */}
                {examples.status === "failed" ? null : (
                  <span
                    className={[
                      "block h-16 w-24 shrink-0 overflow-hidden rounded-[var(--r-control)]",
                      examples.status === "loading" ? "generating" : "bg-canvas",
                    ].join(" ")}
                  >
                    {example ? (
                      <Plot figure={example.figure} interactive={false} compact className="h-full w-full" />
                    ) : examples.status === "loaded" ? (
                      <span className="grid h-full place-items-center px-2 text-center text-[11px] text-muted">
                        No example yet
                      </span>
                    ) : null}
                  </span>
                )}
                <span className="min-w-0">
                  <span className="block text-[13px] font-semibold text-ink">{kind.label}</span>
                  <span className="block text-[12px] text-muted">{kind.best_for}</span>
                  <span className="block text-[11.5px] text-muted">Needs {kind.needs}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
