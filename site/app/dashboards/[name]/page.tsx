import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DASHBOARDS } from "@/components/dashboards";
import { DashboardView } from "@/components/dashboard-view";
import { DASHBOARD_TITLES } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return DASHBOARDS.map((dashboard) => ({ name: dashboard.name }));
}

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }): Promise<Metadata> {
  const { name } = await params;
  return { title: `${DASHBOARD_TITLES[name] ?? name} · PromptDash` };
}

export default async function DashboardPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const dashboard = DASHBOARDS.find((d) => d.name === name);
  if (!dashboard) notFound();
  return (
    <main className="mx-auto max-w-6xl px-4 pb-10 pt-6 sm:px-8">
      <Link href="/#dashboards" className="inline-flex h-11 items-center text-[15px] font-semibold text-pine hover:underline">
        ← All dashboards
      </Link>
      <h1 className="mt-2 font-display text-[32px] font-bold leading-tight sm:text-[40px]">
        {DASHBOARD_TITLES[dashboard.name]}
      </h1>
      <div className="mt-6">
        <DashboardView dashboard={dashboard} />
      </div>
    </main>
  );
}
