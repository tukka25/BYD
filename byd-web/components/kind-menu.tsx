"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  ChartArea,
  ChartBarStacked,
  ChartCandlestick,
  ChartColumn,
  ChartLine,
  ChartNoAxesColumn,
  ChartPie,
  ChartScatter,
  Funnel,
  Grid3x3,
  Hash,
  LayoutDashboard,
  Sun,
  X,
  type LucideIcon,
} from "lucide-react";
import { Chip } from "@/components/ui";
import { CHART_KINDS, type ChartKind } from "@/lib/chart-kinds";
import { filterKinds, removeToken, slashTokenAt, type SlashToken } from "@/lib/slash-menu";

/* One icon per kind, as a label in the menu. The chart kinds panel shows a
   chart the model drew instead; an icon never stands in for a chart. */
export const KIND_ICONS: Record<string, LucideIcon> = {
  kpi: Hash,
  bar: ChartColumn,
  line: ChartLine,
  area: ChartArea,
  scatter: ChartScatter,
  pie: ChartPie,
  histogram: ChartNoAxesColumn,
  box: ChartCandlestick,
  heatmap: Grid3x3,
  treemap: LayoutDashboard,
  sunburst: Sun,
  funnel: Funnel,
  waterfall: ChartBarStacked,
};

/** The "/" menu's state for one field, over the fixed list of kinds
    (CHART_KINDS). Focus never leaves the field: the highlighted option is
    announced through aria-activedescendant. */
export function useKindMenu(onPick: (kind: ChartKind, next: { text: string; caret: number }) => void) {
  const [state, setState] = useState<{ token: SlashToken; index: number } | null>(null);
  const options = useMemo(() => (state ? filterKinds(CHART_KINDS, state.token.query) : []), [state]);
  const active = state && options.length ? options[Math.min(state.index, options.length - 1)] : null;

  function sync(text: string, caret: number) {
    const token = slashTokenAt(text, caret);
    setState(token ? { token, index: 0 } : null);
  }

  function pick(text: string, kind: ChartKind) {
    if (!state) return;
    onPick(kind, removeToken(text, state.token));
    setState(null);
  }

  /** True when the key belonged to the menu, so the field must not act on it. */
  function keyDown(event: KeyboardEvent, text: string): boolean {
    if (!state) return false;
    if (event.key === "Escape") {
      event.preventDefault();
      setState(null);
      return true;
    }
    if (!options.length) return false;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setState({ ...state, index: (state.index + step + options.length) % options.length });
      return true;
    }
    if ((event.key === "Enter" || event.key === "Tab") && active) {
      event.preventDefault();
      pick(text, active);
      return true;
    }
    return false;
  }

  return {
    open: state !== null,
    options,
    active,
    sync,
    pick,
    keyDown,
    close: () => setState(null),
    highlight: (index: number) => setState((current) => (current ? { ...current, index } : current)),
  };
}

export function KindMenu({
  id,
  options,
  active,
  onPick,
  onHighlight,
  placement = "above",
}: {
  id: string;
  options: ChartKind[];
  active: ChartKind | null;
  onPick: (kind: ChartKind) => void;
  onHighlight: (index: number) => void;
  placement?: "above" | "below";
}) {
  const activeRow = useRef<HTMLLIElement | null>(null);
  // Keep the highlighted row visible: the list scrolls and shows about five.
  useEffect(() => {
    activeRow.current?.scrollIntoView({ block: "nearest" });
  }, [active?.kind]);

  return (
    <ul
      id={id}
      role="listbox"
      aria-label="Chart kinds"
      className={[
        "absolute left-0 right-0 z-30 max-h-72 overflow-y-auto rounded-[var(--r-card)] bg-surface p-1.5 shadow-[var(--lift-2)]",
        placement === "above" ? "bottom-full mb-2" : "top-full mt-2",
      ].join(" ")}
    >
      {options.map((option, index) => {
        const Icon = KIND_ICONS[option.kind] ?? ChartColumn;
        const selected = active?.kind === option.kind;
        return (
          <li
            key={option.kind}
            ref={selected ? activeRow : undefined}
            id={`${id}-${option.kind}`}
            role="option"
            aria-selected={selected}
            onMouseDown={(event) => {
              event.preventDefault(); // keep focus in the field
              onPick(option);
            }}
            onMouseEnter={() => onHighlight(index)}
            className={[
              "flex cursor-pointer items-center gap-3 rounded-[var(--r-control)] px-2.5 py-2",
              selected ? "bg-pine-wash" : "hover:bg-sunken",
            ].join(" ")}
          >
            <Icon size={16} strokeWidth={2.25} className={selected ? "text-pine" : "text-muted"} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold text-ink">{option.label}</span>
              <span className="block truncate text-[12px] text-muted">{option.best_for}</span>
            </span>
            <span className="shrink-0 text-[12px] text-muted tabular">/{option.kind}</span>
          </li>
        );
      })}
      {options.length === 0 ? (
        <li role="presentation" className="px-2.5 py-2 text-[12.5px] text-muted">
          No chart kind matches
        </li>
      ) : null}
    </ul>
  );
}

export function KindChip({ kind, onRemove }: { kind: ChartKind; onRemove: () => void }) {
  const Icon = KIND_ICONS[kind.kind] ?? ChartColumn;
  return (
    <Chip tone="pine">
      <Icon size={12} strokeWidth={2.25} />
      {kind.label}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${kind.label}`}
        className="-mr-1 grid size-4 place-items-center rounded-full hover:bg-surface"
      >
        <X size={11} strokeWidth={2.25} />
      </button>
    </Chip>
  );
}
