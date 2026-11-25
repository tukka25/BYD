import Link from "next/link";
import { sourceKinds, type Dashboard } from "@/lib/dashboard";
import { MEASURE } from "@/components/section";
import { DASHBOARD_TITLES } from "@/lib/site";

/* The three dashboards as cards: the title, what the data is, the prompt, and
   a link. No figure is drawn here, so the page loads no charts. Each card is
   one link named by its title; the source kinds sit in a slate chip, the
   app's chip for a neutral category. */
export function DashboardCards({ dashboards }: { dashboards: Dashboard[] }) {
  return (
    <ul className="mt-10 grid gap-4 md:grid-cols-3">
      {dashboards.map((dashboard) => {
        const titleId = `dashboard-card-${dashboard.name}`;
        return (
          <li key={dashboard.name}>
            <Link
              href={`/dashboards/${dashboard.name}/`}
              aria-labelledby={titleId}
              className="group flex h-full flex-col rounded-[var(--r-panel)] bg-surface p-6 shadow-[var(--lift-1)] transition-shadow hover:shadow-[var(--lift-2)] active:translate-y-px"
            >
              <h3 id={titleId} className="font-display text-[21px] font-semibold leading-tight text-ink">
                {DASHBOARD_TITLES[dashboard.name]}
              </h3>
              <p className="mt-2.5">
                <span className="inline-flex rounded-[var(--r-pill)] bg-slate-wash px-2.5 py-0.5 text-[14px] font-semibold text-slate-ink">
                  {sourceKinds(dashboard)}
                </span>
              </p>
              <p className={`mt-4 flex-1 text-[16px] leading-relaxed text-ink ${MEASURE}`}>&ldquo;{dashboard.prompt}&rdquo;</p>
              <span className="mt-5 text-[15px] font-semibold text-pine group-hover:underline group-hover:underline-offset-2">
                Open the dashboard <span aria-hidden="true">→</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
