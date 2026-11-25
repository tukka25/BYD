import airbnb from "@/data/dashboards/airbnb.json";
import netflix from "@/data/dashboards/netflix.json";
import shop from "@/data/dashboards/shop.json";
import { DashboardCards } from "@/components/dashboard-cards";
import { Lede, Section } from "@/components/section";
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
    <Section id="dashboards" title="Three prompts, three dashboards">
      <Lede>
        Each dashboard is the app&apos;s own output, unedited. One prompt went in, typed the way a person would type
        it, and lora-v2 planned and drew every chart. When a build fell short, the prompt was reworded and the
        dashboard built again; each page says whether the prompt shown was the first one tried.
      </Lede>
      <DashboardCards dashboards={DASHBOARDS} />
    </Section>
  );
}
