"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ReportCanvas } from "@/components/report-canvas";
import { getAccessToken } from "@/lib/auth";
import { getReport, type Report } from "@/lib/reports";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    getReport(token, params.id)
      .then(setReport)
      .catch(() => setMissing(true));
  }, [params.id, router]);

  return (
    <AppShell>
      {missing ? (
        <div className="px-8 pt-8">
          <h1 className="font-display text-[28px] font-bold text-ink">Report not found</h1>
          <p className="mt-1.5 text-sm text-muted">
            It may have been deleted, or it belongs to another account.
          </p>
        </div>
      ) : report ? (
        <ReportCanvas report={report} />
      ) : (
        <div className="px-8 pt-8">
          <div className="h-10 w-72 rounded-[var(--r-control)] generating" />
          <div className="mt-6 grid grid-cols-2 gap-4">
            <div className="h-64 rounded-[var(--r-panel)] generating" />
            <div className="h-64 rounded-[var(--r-panel)] generating" />
          </div>
        </div>
      )}
    </AppShell>
  );
}
