import airbnb from "@/data/dashboards/airbnb.json";
import netflix from "@/data/dashboards/netflix.json";
import shop from "@/data/dashboards/shop.json";
import { DashboardTabs } from "@/components/dashboard-tabs";
import { DashboardView } from "@/components/dashboard-view";
import { sourceKinds, validateDashboard, type Dashboard } from "@/lib/dashboard";

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
        planned and drew from it. The code button on a chart shows what the model wrote.
      </p>
      <div className="mt-8">
        <DashboardTabs tabs={DASHBOARDS.map((d) => ({ id: d.name, label: d.title, detail: sourceKinds(d) }))}>
          {DASHBOARDS.map((d) => (
            <DashboardView key={d.name} dashboard={d} />
          ))}
        </DashboardTabs>
      </div>
    </section>
  );
}
