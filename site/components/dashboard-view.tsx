import type { CSSProperties } from "react";
import { DashboardCard } from "@/components/dashboard-card";
import { LazyChart } from "@/components/lazy-chart";
import { Name } from "@/components/section";
import {
  blockHeight,
  buildLine,
  creditNames,
  creditTag,
  gridPlacement,
  isIndicator,
  type Dashboard,
} from "@/lib/dashboard";
import { toHtml } from "@/lib/rich-text";

/* The saved 12-column grid at the canvas's row height and gap. Under 768 px it
   is one column in the saved order, each chart at full width and its saved
   height; notes take the height their text needs.
   data-preview-grid and data-block-kind change nothing on screen: they are how
   scripts/previews.mjs finds the grid and its blocks for the landing page's
   pictures. */
export function DashboardView({ dashboard }: { dashboard: Dashboard }) {
  return (
    <div>
      <div data-preview-grid="" className="flex flex-col gap-4 md:grid md:auto-rows-[44px] md:grid-cols-12">
        {dashboard.blocks.map((block, index) => (
          <div
            key={`${block.y}-${block.x}`}
            data-block-kind={block.kind}
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
   stays in view from tablet width up while you scroll through the dashboard it
   built. The line under it comes from the build record, in words. */
function PromptBox({ dashboard }: { dashboard: Dashboard }) {
  return (
    <div className="z-10 mt-6 md:sticky md:bottom-4">
      <div className="mx-auto max-w-3xl rounded-[var(--r-panel)] bg-surface p-3 shadow-[var(--lift-2)]">
        <p className="px-1 text-[14px] font-semibold text-ink">What should this dashboard be about?</p>
        <p className="mt-1.5 rounded-[var(--r-control)] px-3.5 py-3 text-[16px] leading-relaxed text-ink ring-1 ring-inset ring-hairline">
          {dashboard.prompt}
        </p>
        <p className="mt-2 px-1 text-[14px] leading-snug text-body">{buildLine(dashboard.build)}</p>
      </div>
    </div>
  );
}

const link =
  "inline-flex items-center underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] max-md:min-h-11  decoration-hairline-strong underline-offset-4 hover:text-ink";

/* Where the data came from, as links only: "Data:", each source's name linked
   to its page, a short note where its licence asks for a change to be
   indicated, and one licence (or "synthetic") tag. All read from the file's
   sources. */
function Provenance({ dashboard }: { dashboard: Dashboard }) {
  const { sources, build } = dashboard;
  const tag = creditTag(sources);
  const skipped = build.skipped;
  return (
    <div className="mt-5 space-y-2 px-1 text-[14px] leading-[1.6] text-body [&>*]:max-w-[42ch]">
      <p className="flex flex-wrap items-center gap-x-3">
        <span>Data:</span>
        {creditNames(sources).map(({ name, url, note }) => {
          return (
            <span key={name} className="inline-flex flex-wrap items-center gap-x-1.5">
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer" className={link}>
                  {name}
                </a>
              ) : (
                <span>{name}</span>
              )}
              {note ? <span className="text-muted">({note})</span> : null}
            </span>
          );
        })}
        {tag ? (
          <a href={tag.url} target="_blank" rel="noopener noreferrer" className={link}>
            {tag.text}
          </a>
        ) : null}
      </p>
      <p>
        Drawn by <Name>{dashboard.model.label}</Name>, unedited, on <Name>{dashboard.generated_at.slice(0, 10)}</Name>.
        {skipped.length
          ? ` ${skipped.length} planned chart${skipped.length > 1 ? "s" : ""} could not be drawn: ${skipped
              .map((item) => item.label)
              .join(", ")}.`
          : ""}
      </p>
    </div>
  );
}
