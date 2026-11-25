import airbnb from "@/data/dashboards/airbnb.json";
import netflix from "@/data/dashboards/netflix.json";
import shop from "@/data/dashboards/shop.json";
import { DashboardCards } from "@/components/dashboard-cards";
import { validateDashboard, type Dashboard } from "@/lib/dashboard";

// The footer credits the data from these files too.
export const DASHBOARDS = [airbnb, shop, netflix] as unknown as Dashboard[];

// A broken file fails the build, as the tests would.
for (const dashboard of DASHBOARDS) {
  const problems = validateDashboard(dashboard, new TextEncoder().encode(JSON.stringify(dashboard)).length);
  if (problems.length) throw new Error(`data/dashboards/${dashboard.name}.json: ${problems.join("; ")}`);
}

export function Dashboards() {
  return (
    <section id="dashboards" className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
      <h2 className="font-display text-[30px] font-bold leading-tight sm:text-[36px]">Three prompts, three dashboards</h2>
      <p className="mt-3 max-w-2xl text-[16px] leading-relaxed">
        Each is the app&apos;s own output, unedited: one prompt typed as a person would, and every chart lora-v2
        planned and drew from it. Open one to see it whole.
      </p>
      <DashboardCards dashboards={DASHBOARDS} />
    </section>
  );
}
