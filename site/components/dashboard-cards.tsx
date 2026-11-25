import Link from "next/link";
import previews from "@/data/previews.json";
import { ArrowUpRightIcon } from "@/components/icons";
import { MEASURE } from "@/components/section";
import { sourceKinds, type Dashboard } from "@/lib/dashboard";
import { DASHBOARD_TITLES } from "@/lib/site";

type Preview = { file: string; width: number; height: number };

/* A picture of the top of each dashboard, taken from its own page by
   scripts/previews.mjs. It is the only image of a chart on the site: the
   dashboard pages draw theirs live. A dashboard with no picture yet keeps the
   sunken tile, so a new one can be built before it is captured;
   tests/previews.test.mts fails until it is. */
const PREVIEWS: Record<string, Preview | undefined> = previews.dashboards;

/* From md up the three cards sit like a hand of cards. The middle one is wider
   (the 1.2fr track) and higher; the outer two drop by 18% of their own width,
   so the drop scales with the card, and tilt outward by 2 degrees. Tilt and
   lift live on an inner element that ignores the pointer, so the link's own
   box, which the pointer hits, never moves under it. Literal class strings,
   so Tailwind finds them. */
const PLACES = [
  { item: "md:mt-[18%]", card: "md:-rotate-2" },
  { item: "", card: "" },
  { item: "md:mt-[18%]", card: "md:rotate-2" },
];

/* The three dashboards as cards: a picture of the dashboard with its source
   kinds and an arrow on it, then the title, the prompt and a link. Each card
   is one link named by its title; everything else in it is text or decoration.
   The picture is a WebP file, so the page still loads no charts. */
export function DashboardCards({ dashboards }: { dashboards: Dashboard[] }) {
  return (
    <ul className="mt-10 grid gap-10 md:grid-cols-[1fr_1.2fr_1fr] md:items-start md:gap-5 md:px-3 lg:gap-8">
      {dashboards.map((dashboard, index) => {
        const titleId = `dashboard-card-${dashboard.name}`;
        const preview = PREVIEWS[dashboard.name];
        const place = PLACES[index] ?? PLACES[1];
        return (
          <li key={dashboard.name} className={`max-w-md md:max-w-none ${place.item}`}>
            <Link
              href={`/dashboards/${dashboard.name}/`}
              aria-labelledby={titleId}
              // The focus ring moves to the picture, which straightens and
              // lifts on focus; an outline on the unmoved link box would sit
              // beside it. ! beats the page's global :focus-visible outline.
              className="group block focus-visible:outline-none!"
            >
              <div
                className={`pointer-events-none transition-transform duration-200 ease-[var(--ease-out)] group-hover:-translate-y-1.5 group-hover:rotate-0 group-focus-visible:-translate-y-1.5 group-focus-visible:rotate-0 group-active:-translate-y-0.5 motion-reduce:transition-none ${place.card}`}
              >
                <div className="relative aspect-[4/3] overflow-hidden rounded-[var(--r-panel)] bg-sunken shadow-[var(--lift-2)] ring-1 ring-hairline group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-pine md:aspect-[4/5]">
                  {preview ? (
                    // A plain img: the export serves this file as it is, and
                    // next/image would add client code to do nothing more.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={preview.file}
                      width={preview.width}
                      height={preview.height}
                      loading="lazy"
                      decoding="async"
                      alt=""
                      className="size-full object-cover object-top"
                    />
                  ) : null}
                  <span className="absolute left-3 top-3 inline-flex h-8 items-center rounded-[var(--r-pill)] bg-surface px-3 text-[14px] font-semibold text-slate-ink shadow-[var(--lift-2)]">
                    {sourceKinds(dashboard)}
                  </span>
                  <span
                    aria-hidden="true"
                    className="absolute right-3 top-3 grid size-8 place-items-center rounded-full bg-surface text-ink shadow-[var(--lift-2)] group-hover:bg-pine group-hover:text-white group-focus-visible:bg-pine group-focus-visible:text-white"
                  >
                    <ArrowUpRightIcon />
                  </span>
                </div>
                <h3 id={titleId} className="mt-4 font-display text-[20px] font-semibold leading-tight text-ink">
                  {DASHBOARD_TITLES[dashboard.name]}
                </h3>
                <p className={`mt-1.5 line-clamp-2 text-[16px] leading-normal text-body ${MEASURE}`}>
                  &ldquo;{dashboard.prompt}&rdquo;
                </p>
                <span className="mt-3 inline-block text-[15px] font-semibold text-pine group-hover:underline group-hover:underline-offset-2 group-focus-visible:underline group-focus-visible:underline-offset-2">
                  Open the dashboard <span aria-hidden="true">→</span>
                </span>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
