import type { ReactNode } from "react";
import stats from "@/data/stats.json";
import { Num } from "@/components/num";
import { findStat, type Stat } from "@/lib/stats";

const ALL = stats as unknown as Stat[];

/* One result: what was measured, the id of its number in data/stats.json, and
   whether the fine-tuned model produced it. */
export type Meter = { label: string; id: string; tuned?: boolean };

/* A card of results: what they measure, what they were measured on, and each
   share as a figure with a bar under it. The figure is printed (and linked to
   the file that recorded it), so the bar only shows the share at a glance and
   is hidden from screen readers.
   The base model's bars are gray and the fine-tuned model's pine, each on a
   lighter step of its own colour. Checked with the dataviz palette script:
   the gray (--on-dark-muted) and pine are 28.6 apart for normal vision and
   24.7 under colour blindness, so the two never read as one. The gray is only
   1.9:1 on its track, which the printed figure beside it makes up for.
   Cards side by side stretch to one height, and each list sits at the foot of
   its card, so their rows line up even when one title wraps. */
export function MeterCard({ title, note, meters }: { title: ReactNode; note: ReactNode; meters: Meter[] }) {
  return (
    <div className="flex flex-col rounded-[var(--r-card)] bg-surface px-5 py-4 shadow-[var(--lift-1)]">
      <p className="font-display text-[17px] font-semibold leading-snug text-ink">{title}</p>
      <p className="mt-1 text-[14px] leading-snug text-body">{note}</p>
      <ul className="mt-auto space-y-3 pt-4">
        {meters.map((meter) => {
          const share = Math.min(1, Math.max(0, findStat(ALL, meter.id).value));
          return (
            <li key={meter.id}>
              <p className="flex items-baseline justify-between gap-3">
                <span className="text-[15px] leading-snug text-body">{meter.label}</span>
                <span className="whitespace-nowrap font-display text-[22px] font-bold leading-none text-ink">
                  <Num id={meter.id} decimals={0} />
                </span>
              </p>
              <span
                aria-hidden="true"
                className={`mt-2 block h-2 rounded-full ${meter.tuned ? "bg-pine-wash" : "bg-sunken"}`}
              >
                <span
                  className={`block h-full rounded-full ${meter.tuned ? "bg-pine" : "bg-on-dark-muted"}`}
                  style={{ width: `${share * 100}%` }}
                />
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
