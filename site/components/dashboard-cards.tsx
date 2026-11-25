import Link from "next/link";
import { sourceKinds, type Dashboard } from "@/lib/dashboard";
import { DASHBOARD_TITLES } from "@/lib/site";

/* The three dashboards as cards: the title, what the data is, the prompt, and
   a link. No figure is drawn here, so the page loads no charts. */
export function DashboardCards({ dashboards }: { dashboards: Dashboard[] }) {
  return (
    <ul className="mt-8 grid gap-4 md:grid-cols-3">
      {dashboards.map((dashboard) => (
        <li key={dashboard.name}>
          <Link
            href={`/dashboards/${dashboard.name}/`}
            className="flex h-full flex-col rounded-[var(--r-panel)] bg-surface p-6 shadow-[var(--lift-1)] transition-shadow hover:shadow-[var(--lift-2)]"
          >
            <h3 className="font-display text-[20px] font-semibold leading-tight text-ink">
              {DASHBOARD_TITLES[dashboard.name]}
            </h3>
            <p className="mt-1 font-mono text-[12px] uppercase tracking-[0.14em] text-pine">
              {sourceKinds(dashboard)}
            </p>
            <p className="mt-4 flex-1 text-[15px] leading-relaxed">&ldquo;{dashboard.prompt}&rdquo;</p>
            <span className="mt-5 text-[14px] font-semibold text-pine">Open the dashboard →</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
