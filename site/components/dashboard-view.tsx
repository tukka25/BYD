import type { CSSProperties } from "react";
import { DashboardCard } from "@/components/dashboard-card";
import { LazyChart } from "@/components/lazy-chart";
import { blockHeight, gridPlacement, isIndicator, type Dashboard } from "@/lib/dashboard";
import { toHtml } from "@/lib/rich-text";

/* The saved 12-column grid at the canvas's row height and gap. Under 768 px it
   is one column in the saved order, each chart at full width and its saved
   height; notes take the height their text needs. */
export function DashboardView({ dashboard }: { dashboard: Dashboard }) {
  return (
    <div>
      <div className="flex flex-col gap-4 md:grid md:auto-rows-[44px] md:grid-cols-12">
        {dashboard.blocks.map((block, index) => (
          <div
            key={`${block.y}-${block.x}`}
            style={{ ...gridPlacement(block), "--block-h": `${blockHeight(block.h)}px` } as CSSProperties}
            className={block.kind === "text" ? "md:h-auto" : "h-[var(--block-h)] md:h-auto"}
          >
            <DashboardCard title={block.title} code={block.code}>
              {block.kind === "text" ? (
                <div
                  className="rich-text size-full overflow-auto px-2 py-1 text-sm leading-relaxed text-body"
                  // Sanitised by the app's own sanitiser (lib/rich-text.ts), as the app does on render.
                  dangerouslySetInnerHTML={{ __html: toHtml(block.text_body) }}
                />
              ) : (
                <LazyChart
                  dashboard={dashboard.name}
                  index={index}
                  currency={dashboard.currency}
                  indicator={isIndicator(block)}
                />
              )}
            </DashboardCard>
          </div>
        ))}
      </div>
      <PromptBox dashboard={dashboard} />
      <Provenance dashboard={dashboard} />
    </div>
  );
}

/* The prompt, frozen below its dashboard: the app's brief box, read-only. It
   stays in view from tablet width up while you scroll through the dashboard it built. */
function PromptBox({ dashboard }: { dashboard: Dashboard }) {
  const { build } = dashboard;
  const rephrased = build.prompts_tried - 1;
  return (
    <div className="z-10 mt-6 md:sticky md:bottom-4">
      <div className="mx-auto max-w-3xl rounded-[var(--r-panel)] bg-surface p-3 shadow-[var(--lift-2)]">
        <p className="px-1 text-[13px] font-semibold text-ink">What should this dashboard be about?</p>
        <p className="mt-1.5 rounded-[var(--r-control)] px-3.5 py-3 text-sm text-ink ring-1 ring-inset ring-hairline">
          {dashboard.prompt}
        </p>
        <p className="mt-2 px-1 text-[12px] text-muted tabular">
          Sent as typed · {build.charts_drawn} of {build.charts_planned} charts drawn · {Math.round(build.seconds)} s on
          a Mac
          {rephrased > 0 ? ` · after ${rephrased} rephrasing${rephrased > 1 ? "s" : ""}` : ""}
        </p>
      </div>
    </div>
  );
}

function Provenance({ dashboard }: { dashboard: Dashboard }) {
  const notes = [...new Set(dashboard.sources.map((source) => source.note))].join(" ");
  const skipped = dashboard.build.skipped;
  const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";
  return (
    <div className="mt-4 space-y-1 px-1 text-[12.5px] leading-relaxed text-muted">
      <p>
        Data:{" "}
        {dashboard.sources.map((source, i) => (
          <span key={source.name}>
            {i > 0 ? "; " : ""}
            <a href={source.url} className={link}>
              {source.name}
            </a>{" "}
            ({source.rows.toLocaleString("en-US")} rows,{" "}
            {source.licence_url ? (
              <a href={source.licence_url} className={link}>
                {source.licence}
              </a>
            ) : (
              source.licence
            )}
            )
          </span>
        ))}
        . {notes}
      </p>
      <p>
        Drawn by {dashboard.model.label}, unedited, on {dashboard.generated_at.slice(0, 10)}.
        {skipped.length
          ? ` ${skipped.length} planned chart${skipped.length > 1 ? "s" : ""} could not be drawn: ${skipped
              .map((item) => item.label)
              .join(", ")}.`
          : ""}
      </p>
    </div>
  );
}
