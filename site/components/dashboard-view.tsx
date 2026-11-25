import type { CSSProperties } from "react";
import { DashboardCard } from "@/components/dashboard-card";
import { LazyChart } from "@/components/lazy-chart";
import { KeepDates, Name } from "@/components/section";
import {
  blockHeight,
  buildLine,
  capitalise,
  gridPlacement,
  isIndicator,
  licences,
  splitNotes,
  type Dashboard,
} from "@/lib/dashboard";
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

const link = "underline decoration-hairline-strong underline-offset-2 hover:text-ink";

function LicenceText({ licence, licence_url }: { licence: string; licence_url: string }) {
  const text = capitalise(licence);
  return licence_url ? (
    <a href={licence_url} className={link}>
      {text}
    </a>
  ) : (
    <>{text}</>
  );
}

/* Where the data came from. A sentence every source's note shares is said
   once, with a licence every source shares; what is left of each note sits
   beside its own source. */
function Provenance({ dashboard }: { dashboard: Dashboard }) {
  const { sources, build } = dashboard;
  const { shared, own } = splitNotes(sources.map((source) => source.note));
  const common = licences(sources);
  const oneLicence = common.length === 1 ? common[0] : null;
  const skipped = build.skipped;
  const name = (index: number) => (
    <a href={sources[index].url} className={link}>
      {sources[index].name}
    </a>
  );
  return (
    <div className="mt-5 space-y-2 px-1 text-[14px] leading-[1.6] text-body">
      {shared || oneLicence ? (
        <p>
          <KeepDates text={shared} />
          {shared && oneLicence ? " " : ""}
          {oneLicence ? (
            <>
              <LicenceText {...oneLicence} />.
            </>
          ) : null}
        </p>
      ) : null}
      {own.some(Boolean) || !oneLicence ? (
        <ul className="space-y-1">
          {sources.map((source, index) => (
            <li key={source.name}>
              {name(index)}
              {oneLicence ? null : (
                <>
                  {" "}
                  (<LicenceText {...source} />)
                </>
              )}
              {own[index] ? (
                <>
                  : <KeepDates text={own[index]} />
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p>
          Data:{" "}
          {sources.map((source, index) => (
            <span key={source.name}>
              {index > 0 ? ", " : ""}
              {name(index)}
            </span>
          ))}
          .
        </p>
      )}
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
