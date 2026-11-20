"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Database, FileText, Plus } from "lucide-react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { Button, Chip, EmptyState, Panel } from "@/components/ui";
import { getAccessToken } from "@/lib/auth";
import { listReports, type Report } from "@/lib/reports";
import { authorizedFetch } from "@/lib/backend";

interface SourceRow {
  id: string;
  display_name: string;
  original_filename?: string | null;
}

export default function HomePage() {
  const [reports, setReports] = useState<Report[] | null>(null);
  const [sources, setSources] = useState<SourceRow[]>([]);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    listReports(token)
      .then(setReports)
      .catch(() => setReports([]));
    authorizedFetch<SourceRow[]>("/api/v1/data-sources", token)
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  return (
    <AppShell>
      <PageHeader
        title="Reports"
        lead="Each report is a canvas. Ask a question, and the answer arrives as a block you can move, resize and export."
        actions={
          <Link href="/reports/new">
            <Button variant="primary">
              <Plus size={16} strokeWidth={2.25} />
              New report
            </Button>
          </Link>
        }
      />

      <div className="app-scroll px-5 pb-16 sm:px-8">
        {reports === null ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div className="h-36 rounded-[var(--r-panel)] generating" />
            <div className="h-36 rounded-[var(--r-panel)] generating" />
            <div className="h-36 rounded-[var(--r-panel)] generating" />
          </div>
        ) : reports.length === 0 ? (
          <Panel>
            <EmptyState
              icon={<FileText size={20} strokeWidth={2.25} />}
              title="No reports yet"
              body={
                sources.length > 0
                  ? `You have ${sources.length} data source${sources.length === 1 ? "" : "s"} ready. Create a report and start asking questions.`
                  : "Upload a CSV or Excel file first, then create a report and ask it questions."
              }
              action={
                <div className="flex items-center gap-2">
                  <Link href="/reports/new">
                    <Button variant="primary">Create a report</Button>
                  </Link>
                  <Link href="/data">
                    <Button variant="secondary">Add data</Button>
                  </Link>
                </div>
              }
            />
          </Panel>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {reports.map((report) => (
              <Link key={report.id} href={`/reports/${report.id}`} className="group">
                <Panel className="flex h-full flex-col p-5 transition-shadow duration-200 ease-[var(--ease-out)] group-hover:shadow-[var(--lift-2)]">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-display text-[19px] font-semibold leading-snug text-ink">
                      {report.title}
                    </h2>
                    <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-sunken text-muted transition-colors duration-200 group-hover:bg-pine group-hover:text-white">
                      <ArrowRight size={15} strokeWidth={2.25} />
                    </span>
                  </div>
                  {report.description ? (
                    <p className="mt-2 line-clamp-2 text-[13.5px] leading-relaxed text-muted">
                      {report.description}
                    </p>
                  ) : null}
                  <div className="mt-auto flex items-center gap-2 pt-5">
                    <Chip tone={report.dataSourceIds.length > 0 ? "slate" : "neutral"}>
                      <Database size={11} strokeWidth={2.25} />
                      {report.dataSourceIds.length > 0
                        ? `${report.dataSourceIds.length} source${report.dataSourceIds.length === 1 ? "" : "s"}`
                        : "Any source"}
                    </Chip>
                    <span className="text-[12px] text-muted tabular">
                      {new Date(report.updatedAt).toLocaleDateString(undefined, {
                        day: "numeric",
                        month: "short",
                      })}
                    </span>
                  </div>
                </Panel>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
