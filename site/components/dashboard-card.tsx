"use client";

import { useState, type ReactNode } from "react";
import { CodeIcon } from "@/components/icons";

/* A block as the app's View mode draws it (BlockFrame in report-canvas.tsx):
   the title, the chart or note, and the button that shows the code the model
   wrote. As in the app, showing the code replaces the chart until it is hidden. */
export function DashboardCard({ title, code, children }: { title: string; code: string | null; children: ReactNode }) {
  const [showCode, setShowCode] = useState(false);
  const label = showCode ? "Hide the code" : "Show the code that drew this";

  return (
    <section
      aria-label={title}
      className="flex h-full flex-col overflow-hidden rounded-[var(--r-panel)] bg-surface shadow-[var(--lift-1)]"
    >
      <header className="flex items-start gap-2 px-5 pt-4">
        <h3 className="min-w-0 flex-1 truncate font-display text-[15px] font-semibold leading-tight text-ink" title={title}>
          {title}
        </h3>
        {code ? (
          <button
            type="button"
            onClick={() => setShowCode((shown) => !shown)}
            aria-pressed={showCode}
            aria-label={label}
            title={label}
            className={`relative grid size-8 shrink-0 cursor-pointer place-items-center rounded-[var(--r-control)] transition-colors after:absolute after:-inset-1.5 ${
              showCode ? "bg-pine-wash text-pine" : "text-muted hover:bg-sunken hover:text-ink"
            }`}
          >
            <CodeIcon />
          </button>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 px-3 pb-3 pt-2">
        {showCode && code ? (
          <pre className="size-full overflow-auto rounded-[var(--r-card)] bg-inverse p-4 font-mono text-[11.5px] leading-relaxed text-on-dark">
            <code>{code}</code>
          </pre>
        ) : (
          children
        )}
      </div>
    </section>
  );
}
