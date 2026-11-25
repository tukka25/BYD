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
        Each dashboard below came out of one run of PromptDash. The model planned every chart and wrote the code
        that drew it, and I edited nothing by hand.
      </Lede>
      <DashboardCards dashboards={DASHBOARDS} />
    </Section>
  );
}
