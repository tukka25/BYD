"use client";

import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export type Tab = { id: string; label: string; detail: string };

/* One dashboard at a time. The hidden ones stay in the page's HTML, and their
   charts load the first time their tab opens. Arrow keys move between tabs. */
export function DashboardTabs({ tabs, children }: { tabs: Tab[]; children: ReactNode[] }) {
  const [active, setActive] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (active + step + tabs.length) % tabs.length;
    setActive(next);
    buttons.current[next]?.focus();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label="Dashboards"
        onKeyDown={onKeyDown}
        className="inline-flex max-w-full gap-1 overflow-x-auto rounded-[var(--r-pill)] bg-sunken p-1"
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
            aria-selected={index === active}
            tabIndex={index === active ? 0 : -1}
            onClick={() => setActive(index)}
            className={`whitespace-nowrap rounded-[var(--r-pill)] px-4 py-2 text-[13.5px] font-semibold transition-colors ${
              index === active ? "bg-surface text-ink shadow-[var(--lift-1)]" : "text-muted hover:text-ink"
            }`}
          >
            {tab.label} <span className="font-normal text-muted">· {tab.detail}</span>
          </button>
        ))}
      </div>
      {children.map((child, index) => (
        <div
          key={tabs[index].id}
          role="tabpanel"
          id={`panel-${tabs[index].id}`}
          aria-labelledby={`tab-${tabs[index].id}`}
          hidden={index !== active}
          className="mt-6"
        >
          {child}
        </div>
      ))}
    </div>
  );
}
